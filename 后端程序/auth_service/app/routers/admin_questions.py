"""受控题库：录入、审核、版本修订和 OJ 测试数据生命周期。"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import delete, false, func, select, update
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from ..models import (
    AdminUser,
    AuditEvent,
    ChoiceOption,
    FillAnswer,
    LessonProblemBlock,
    Paper,
    PaperQuestion,
    Problem,
    ProblemDryRun,
    ProblemTag,
    ProgrammingDetail,
    ReferenceSolution,
    Tag,
    TestCase,
    TestDataPackage,
    Video,
)
from ..oj_testdata import build_config_yaml, parse_testdata_zip, write_testdata_files
from ..permissions import EDITOR_ROLES, REVIEWER_ROLES, SUPER_ROLE
from ..permissions import is_editor as _is_editor
from ..permissions import is_reviewer as _is_reviewer
from ..permissions import is_super as _is_super
from ..schemas import (
    BLANK_KEY_RE,
    CreateTagPayload,
    ImportedCasesPayload,
    ProblemPayload,
    RejectProblemPayload,
    TestcaseLimitsPayload,
    TransferProblemOwnerPayload,
)
from ..scoring import parse_blank_alternatives
from .admin_auth import audit, client_ip, current_admin, db_session, limit, require_csrf

router = APIRouter(prefix="/api/admin", tags=["admin-questions"])

TAG_CATEGORIES = ("knowledge", "stage", "business")
# 题干、解析和选项内容在库里存 Markdown 源码，入库时不做净化：Markdown 里 `<` 是合法正文
# （`#include <iostream>`、`vector<int>`），按标签剥离会把代码打断。XSS 由渲染出口统一负责，
# 见 前端程序/study-blog-vue/public/admin/vendor/README.md。
_MD_FENCE_RE = re.compile(r"^[ \t]*(?:```|~~~).*$", re.M)  # 只去围栏行，围栏内的正文保留
_MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
# 内联 <img>。尺寸档位一度把 `![](...)` 改写成这个形状（现在改回 alt 后缀写法，见前端
# admin-markdown.js 的 IMAGE_WIDTHS），库里可能还留着那阵子存下的题干。少了这条，
# 一道纯图题的列表标题会是一整行 `<img src="/media/…" width="50%">`——
# _markdown_text() 刻意不剥 `<...>`（为了 `vector<int>`），单挑 img 出来剥是安全的。
_HTML_IMAGE_RE = re.compile(r"<img\b[^>]*>", re.I)
_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_MD_HEADING_RE = re.compile(r"^[ \t]*#{1,6}[ \t]+", re.M)
_MD_QUOTE_RE = re.compile(r"^[ \t]*>[ \t]?", re.M)
_MD_LIST_RE = re.compile(r"^[ \t]*(?:[-*+]|\d+\.)[ \t]+", re.M)
_MD_RULE_RE = re.compile(r"^[ \t]*(?:-{3,}|\*{3,}|_{3,})[ \t]*$", re.M)
_MD_TABLE_DIVIDER_RE = re.compile(r"^[ \t]*\|?[ \t:|-]*-{2,}[ \t:|-]*$", re.M)
_MD_MARKS_RE = re.compile(r"\*{1,3}|~~|`+|\|")


def _markdown_text(value: str) -> str:
    """把 Markdown 源码压成纯文本，用于派生标题和判空——不用于渲染。

    刻意不剥 `<...>`：题面里 `vector<int>`、`#include <iostream>` 比裸 HTML 常见得多，
    按标签剥离会把它们吃掉。派生出的 title 只作纯文本展示，留着标签也无害。
    """
    text = value or ""
    for pattern in (_MD_RULE_RE, _MD_TABLE_DIVIDER_RE, _MD_FENCE_RE, _MD_IMAGE_RE, _HTML_IMAGE_RE, BLANK_KEY_RE):
        text = pattern.sub(" ", text)
    text = _MD_LINK_RE.sub(r"\1", text)
    for pattern in (_MD_HEADING_RE, _MD_QUOTE_RE, _MD_LIST_RE, _MD_MARKS_RE):
        text = pattern.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def _any_image(value: str) -> bool:
    """这段 Markdown 里有没有图。两种载体都算——`![](...)` 是现行写法，`<img>` 是旧数据。"""
    text = value or ""
    return bool(_MD_IMAGE_RE.search(text) or _HTML_IMAGE_RE.search(text))


def _has_content(value: str) -> bool:
    """这段 Markdown 算不算"填了东西"。判空一律走这里，别再直接 `not _markdown_text(...)`。

    图片单独算数：几何题、图形推理题的题干就是一张图加一句"如图"，甚至只有一张图；
    图形选择题的选项本身就是四张图。而 _markdown_text() 会把 `![](...)` 整个剥掉——
    直接拿它判空，纯图题干会被判成"没填题干"而提交不了审核。

    题干与选项两处判空曾经各写各的，这个函数就是把它们收成一处。
    """
    return bool(_markdown_text(value) or _any_image(value))


def _display_title(problem_type: str, stem: str) -> str:
    """列表里那一行的标题。纯图题干派生不出文字，给一个能认出来的占位而不是空白。"""
    text = _markdown_text(stem)
    if text:
        return text[:200]
    label = {"choice": "单选题", "multi_choice": "多选题", "judge": "判断题",
             "fill": "填空题", "programming": "操作题"}.get(problem_type, "题目")
    return f"[图片{label}]" if _any_image(stem) else ""


def _forbid(message: str = "没有执行该题库操作的权限。") -> None:
    raise HTTPException(403, message)


def _can_read(problem: Problem, admin: AdminUser) -> bool:
    if _is_super(admin):
        return True
    if problem.created_by == admin.id or problem.owner_id == admin.id:
        return True
    return admin.role in REVIEWER_ROLES and problem.status == "pending"


def _can_edit_draft(problem: Problem, admin: AdminUser) -> bool:
    return problem.status == "draft" and (_is_super(admin) or (admin.role in EDITOR_ROLES and problem.owner_id == admin.id))


def _open_revision(db: Session, problem: Problem) -> Problem | None:
    """返回该已发布题目正在修订中的副本；同一时刻最多允许一个。"""
    if problem.status != "approved":
        return None
    return db.scalar(
        select(Problem).where(
            Problem.root_problem_id == problem.id,
            Problem.id != problem.id,
            Problem.status.in_(("draft", "pending")),
        )
    )


def _reference_blockers(db: Session, problem: Problem) -> list[str]:
    """返回阻止删除的引用来源；有任何一条就不允许删除。

    组卷（M5）已落地：凡引用了该题编号的试卷都是阻塞源（试卷标题）。
    配课节点（M3）已落地（课中练习单题化 v2 §4.5）：被 lesson_problem_blocks
    引用的题禁止删除——与试卷删除保护（admin_papers._paper_delete_blocker 事前阻止）
    同范式：引用存在即不允许删，删除侧不依赖发布检查兜底。
    删除接口本身不必再动。
    """
    if not problem.problem_id_no:
        return []  # 未发布的题不可能被引用
    blockers = list(db.scalars(
        select(Paper.title)
        .join(PaperQuestion, PaperQuestion.paper_id == Paper.id)
        .where(PaperQuestion.problem_id_no == problem.problem_id_no)
        .limit(5)
    ))
    lesson_refs = db.scalar(
        select(func.count())
        .select_from(LessonProblemBlock)
        .where(LessonProblemBlock.problem_id_no == problem.problem_id_no)
    ) or 0
    if lesson_refs:
        blockers.append(f"该题目已被 {lesson_refs} 个课中练习块引用，请先解绑再删除")
    return blockers


def _allowed_actions(problem: Problem, admin: AdminUser, open_revision: Problem | None = None) -> list[str]:
    actions = ["view"] if _can_read(problem, admin) else []
    if _can_edit_draft(problem, admin):
        actions += ["edit", "submit", "delete"]
    # 审核不再看作者：自审、他审都允许，细粒度权限留到 RBAC 收口时再做。
    if problem.status == "pending" and _is_reviewer(admin):
        actions += ["approve", "reject"]
    if problem.status == "approved" and (_is_super(admin) or problem.owner_id == admin.id):
        # 已发布题不直接改：revise 出一份草稿副本，线上内容在副本通过审核前保持不变。
        actions += ["delete"] if open_revision is None else []
        actions += ["revise"] if open_revision is None else ["view_revision"]
    if _is_super(admin) and problem.status in {"draft", "pending"}:
        actions += ["transfer_owner"]
    return actions


def _require_action(db: Session, problem: Problem, admin: AdminUser, action: str) -> None:
    if action not in _allowed_actions(problem, admin, _open_revision(db, problem)):
        _forbid()


def _lock_problem(db: Session, problem_id: int) -> Problem:
    problem = db.scalar(select(Problem).where(Problem.id == problem_id).with_for_update())
    if not problem:
        raise HTTPException(404, "题目不存在。")
    return problem


def _require_revision(request: Request, problem: Problem) -> None:
    raw = (request.headers.get("If-Match") or "").strip().strip('"')
    if not raw:
        raise HTTPException(428, "请携带 If-Match 题目版本号。")
    try:
        expected = int(raw)
    except ValueError as exc:
        raise HTTPException(400, "If-Match 必须是整数版本号。") from exc
    if expected != problem.revision:
        raise HTTPException(409, {"message": "题目已被其他人更新，请重新加载后再试。", "revision": problem.revision})


def _touch(problem: Problem) -> None:
    problem.revision += 1


def _person_payload(db: Session, admin_id: int | None) -> dict | None:
    admin = db.get(AdminUser, admin_id) if admin_id else None
    return {"id": admin.id, "display_name": admin.display_name} if admin else None


def _audit_problem(db: Session, request: Request, event: str, outcome: str, admin: AdminUser, problem: Problem, **summary):
    audit(
        db,
        request.app.state.settings,
        event,
        outcome,
        client_ip(request),
        admin.id,
        resource_type="problem",
        resource_id=problem.id,
        summary={"status": problem.status, "revision": problem.revision, **summary},
    )


def _remove_testdata_storage(settings, storage_dir: str | None) -> None:
    if not storage_dir:
        return
    root = Path(settings.testdata_upload_root).resolve()
    candidate = Path(storage_dir)
    target = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    if target != root and root in target.parents:
        shutil.rmtree(target, ignore_errors=True)


def _apply_tags(db: Session, problem_id: int, payload: ProblemPayload) -> None:
    names_by_category = {
        category: list(dict.fromkeys(getattr(payload.common, category))) for category in TAG_CATEGORIES
    }
    requested = [(category, name) for category, names in names_by_category.items() for name in names]
    if requested:
        existing = db.scalars(
            select(Tag).where(
                Tag.category.in_(TAG_CATEGORIES),
                Tag.name.in_([name for _, name in requested]),
            )
        ).all()
        index = {(tag.category, tag.name): tag for tag in existing}
        missing = [name for category, name in requested if (category, name) not in index]
        if missing:
            raise HTTPException(422, "标签不存在，请先由超级管理员维护标签：" + "、".join(sorted(set(missing))))
    else:
        index = {}
    db.execute(delete(ProblemTag).where(ProblemTag.problem_id == problem_id))
    for category, name in requested:
        db.add(ProblemTag(problem_id=problem_id, tag_id=index[(category, name)].id))


def _apply_sub_rows(db: Session, problem: Problem, payload: ProblemPayload, previous_type: str, previous_sub_type: str | None) -> list[str]:
    """写入当前题型的数据并返回应在提交后清理的旧 ZIP 目录。"""
    cleanup_dirs: list[str] = []
    db.execute(delete(ChoiceOption).where(ChoiceOption.problem_id == problem.id))
    db.execute(delete(FillAnswer).where(FillAnswer.problem_id == problem.id))

    if payload.type in {"choice", "multi_choice", "judge"}:
        labels = ("A", "B", "C", "D", "E", "F", "G", "H")
        for index, option in enumerate(payload.options):
            db.add(ChoiceOption(problem_id=problem.id, option_label=labels[index], content=option.content.strip(), is_correct=option.is_correct, sort_order=index))
    elif payload.type == "fill":
        for blank in payload.blanks:
            # 与标准答案重复的写法直接丢掉：留着只会让录题人以为自己多设了一种
            others = [item for item in blank.alternatives if item != blank.answer.strip()]
            db.add(FillAnswer(problem_id=problem.id, blank_index=blank.blank_index, blank_key=blank.blank_key,
                              answer=blank.answer.strip(),
                              alternatives_json=json.dumps(others, ensure_ascii=False) if others else None))

    if payload.type != "programming":
        package = db.get(TestDataPackage, problem.id)
        if package:
            cleanup_dirs.append(package.storage_dir)
            db.delete(package)
        db.execute(delete(ProgrammingDetail).where(ProgrammingDetail.problem_id == problem.id))
        db.execute(delete(ReferenceSolution).where(ReferenceSolution.problem_id == problem.id))
        db.execute(delete(TestCase).where(TestCase.problem_id == problem.id))
        return cleanup_dirs

    prog = payload.programming
    assert prog is not None
    # C++→Python 时 ZIP 数据不再有合法归属，立即从数据库脱钩并在提交后清理文件。
    package = db.get(TestDataPackage, problem.id)
    if package and payload.sub_type != "cpp":
        cleanup_dirs.append(package.storage_dir)
        db.delete(package)
        db.execute(delete(TestCase).where(TestCase.problem_id == problem.id, TestCase.input_file.is_not(None)))

    detail = db.get(ProgrammingDetail, problem.id)
    if not detail:
        detail = ProgrammingDetail(problem_id=problem.id)
        db.add(detail)
    detail.input_format = prog.input_format.strip()
    detail.output_format = prog.output_format.strip()
    detail.hints = prog.hints.strip() or "无"
    detail.pass_condition = prog.pass_condition
    detail.time_limit_ms = prog.time_limit_ms
    detail.memory_limit_mb = prog.memory_limit_mb

    db.execute(delete(ReferenceSolution).where(ReferenceSolution.problem_id == problem.id))
    for language, code in (("cpp", prog.ref_code.cpp), ("python", prog.ref_code.python)):
        if code.strip():
            db.add(ReferenceSolution(problem_id=problem.id, language=language, code=code))

    # 仅替换浏览器可维护的公开样例和 Python 手工隐藏测试点，绝不删 ZIP 文件测试点。
    db.execute(delete(TestCase).where(TestCase.problem_id == problem.id, TestCase.input_file.is_(None)))
    order = 0
    for sample in prog.samples:
        # 样例恒继承题目级限制（两列留 null），理由见 SamplePayload 的注释
        db.add(TestCase(problem_id=problem.id, input=sample.input, output=sample.output, is_sample=True, sort_order=order))
        order += 1
    for case in prog.manual_test_cases:
        db.add(TestCase(problem_id=problem.id, input=case.input, output=case.output, is_sample=False, sort_order=order,
                        time_limit_ms=case.time_limit_ms, memory_limit_mb=case.memory_limit_mb))
        order += 1
    return cleanup_dirs


def _submission_error(problem: Problem, db: Session) -> str | None:
    if not _has_content(problem.stem):
        return "请填写题干后再提交审核。"
    if problem.type in {"choice", "multi_choice"}:
        options = db.scalars(select(ChoiceOption).where(ChoiceOption.problem_id == problem.id).order_by(ChoiceOption.sort_order)).all()
        correct_count = sum(option.is_correct for option in options)
        if len(options) < 2 or any(not _has_content(option.content) for option in options):
            return "请至少填写两个完整选项后再提交审核。"
        if problem.type == "choice" and correct_count != 1:
            return "单选题必须且只能设置一个正确答案。"
        if problem.type == "multi_choice" and correct_count < 1:
            return "多选题至少需要一个正确答案。"
    elif problem.type == "judge":
        options = db.scalars(select(ChoiceOption).where(ChoiceOption.problem_id == problem.id).order_by(ChoiceOption.sort_order)).all()
        if [item.content for item in options] != ["对", "错"] or sum(item.is_correct for item in options) != 1:
            return "判断题必须保留“对/错”一对选项和一个正确答案。"
    elif problem.type == "fill":
        keys = BLANK_KEY_RE.findall(problem.stem)
        answers = db.scalars(select(FillAnswer).where(FillAnswer.problem_id == problem.id).order_by(FillAnswer.blank_index)).all()
        if not keys or len(set(keys)) != len(keys) or [item.blank_key for item in answers] != keys:
            return "填空题的空位标记与标准答案必须按顺序一一对应。"
        if [item.blank_index for item in answers] != list(range(len(keys))) or any(not item.answer.strip() for item in answers):
            return "请填写每个空位的标准答案。"
    else:
        detail = db.get(ProgrammingDetail, problem.id)
        solution = db.scalar(select(ReferenceSolution).where(ReferenceSolution.problem_id == problem.id, ReferenceSolution.language == problem.sub_type))
        if not detail or not all((_markdown_text(problem.title), detail.input_format.strip(), detail.output_format.strip(), solution and solution.code.strip())):
            return "请补全操作题标题、输入输出格式和所选语言的参考代码。"
        samples = db.scalars(select(TestCase).where(TestCase.problem_id == problem.id, TestCase.is_sample.is_(True))).all()
        if detail.pass_condition in {"样例通过", "全测试点通过"} and (not samples or any(not item.input.strip() or not item.output.strip() for item in samples)):
            return "选择样例通过或全测试点通过时，至少需要一组完整公开样例。"
        if detail.pass_condition == "全测试点通过":
            if problem.sub_type == "cpp":
                package = db.get(TestDataPackage, problem.id)
                has_files = db.scalar(select(func.count()).select_from(TestCase).where(TestCase.problem_id == problem.id, TestCase.input_file.is_not(None)))
                if not package or not has_files:
                    return "C++ 全测试点通过必须上传 ZIP 测试数据。"
            else:
                cases = db.scalars(select(TestCase).where(TestCase.problem_id == problem.id, TestCase.is_sample.is_(False), TestCase.input_file.is_(None))).all()
                if not cases or any(not item.input.strip() or not item.output.strip() for item in cases):
                    return "Python 全测试点通过至少需要一组完整隐藏测试点。"
            # 只对「全测试点通过」型强制试跑：这类题的成绩完全由测试数据决定，
            # 而在此之前**没有任何一步会去编译参考代码**——一份粘贴时丢了半行的 C++
            # 可以一路通过审核、进卷、发给学员。
            # 不一刀切到所有操作题：「编译通过」型没有测试数据可跑，把门槛设成一刀切
            # 只会逼录题人去改 pass_condition 绕过去。
            latest = db.scalar(
                select(ProblemDryRun)
                .where(ProblemDryRun.problem_id == problem.id,
                       ProblemDryRun.scope == "all",
                       ProblemDryRun.language == problem.sub_type)
                .order_by(ProblemDryRun.id.desc())
            )
            if latest is None or latest.status != "accepted":
                return "请先用参考代码完整试跑一次并全部通过，再提交审核。"
            # 绑 revision 而不是时间戳：时间戳只能证明"试跑发生在保存之后"，
            # 证明不了跑的是哪一版。revision 是每次写操作都 +1 的乐观锁版本。
            if latest.problem_revision != problem.revision:
                return "试跑之后题目又改过，请重新试跑通过后再提交审核。"
    return None


def _problem_to_payload(problem: Problem, db: Session, admin: AdminUser) -> dict:
    tags = db.scalars(select(Tag).join(ProblemTag, ProblemTag.tag_id == Tag.id).where(ProblemTag.problem_id == problem.id)).all()
    revision_draft = _open_revision(db, problem)
    payload = {
        "id": problem.id, "type": problem.type, "sub_type": problem.sub_type, "status": problem.status,
        "revision": problem.revision, "version_no": problem.version_no, "root_problem_id": problem.root_problem_id or problem.id,
        "allowed_actions": _allowed_actions(problem, admin, revision_draft), "problem_id_no": problem.problem_id_no,
        "open_revision": {"id": revision_draft.id, "status": revision_draft.status} if revision_draft else None,
        "owner": _person_payload(db, problem.owner_id), "created_by": _person_payload(db, problem.created_by),
        "reviewed_by": _person_payload(db, problem.reviewed_by), "reviewed_at": problem.reviewed_at,
        "rejection": {"by": _person_payload(db, problem.rejected_by), "at": problem.rejected_at, "reason": problem.rejection_reason} if problem.rejection_reason else None,
        "common": {"difficulty": problem.difficulty, "source": problem.source, "structure": problem.structure,
                   "knowledge": [tag.name for tag in tags if tag.category == "knowledge"], "stage": [tag.name for tag in tags if tag.category == "stage"], "business": [tag.name for tag in tags if tag.category == "business"]},
        "stem": problem.stem, "analysis": problem.analysis,
        "analysis_video_id": problem.analysis_video_id,
        "has_analysis_video": bool(problem.analysis_video_id),
        "analysis_video_status": _analysis_video_status(db, problem.analysis_video_id),
        "options": [{"content": item.content, "is_correct": item.is_correct} for item in db.scalars(select(ChoiceOption).where(ChoiceOption.problem_id == problem.id).order_by(ChoiceOption.sort_order))],
        "blanks": [{"blank_index": item.blank_index, "blank_key": item.blank_key, "answer": item.answer, "alternatives": parse_blank_alternatives(item.alternatives_json)} for item in db.scalars(select(FillAnswer).where(FillAnswer.problem_id == problem.id).order_by(FillAnswer.blank_index))],
    }
    detail = db.get(ProgrammingDetail, problem.id)
    if detail:
        ref = {item.language: item.code for item in db.scalars(select(ReferenceSolution).where(ReferenceSolution.problem_id == problem.id))}
        samples = db.scalars(select(TestCase).where(TestCase.problem_id == problem.id, TestCase.is_sample.is_(True)).order_by(TestCase.sort_order)).all()
        manual = db.scalars(select(TestCase).where(TestCase.problem_id == problem.id, TestCase.is_sample.is_(False), TestCase.input_file.is_(None)).order_by(TestCase.sort_order)).all()
        payload["programming"] = {"title": problem.title, "pass_condition": detail.pass_condition, "input_format": detail.input_format, "output_format": detail.output_format, "hints": detail.hints,
                                  "time_limit_ms": detail.time_limit_ms, "memory_limit_mb": detail.memory_limit_mb,
                                  "samples": [{"input": item.input, "output": item.output} for item in samples],
                                  "manual_test_cases": [{"input": item.input, "output": item.output, "time_limit_ms": item.time_limit_ms, "memory_limit_mb": item.memory_limit_mb} for item in manual],
                                  "ref_code": {"cpp": ref.get("cpp", ""), "python": ref.get("python", "")}}
        package = db.get(TestDataPackage, problem.id)
        if package:
            payload["programming"]["testdata_package"] = {"archive_name": package.archive_name, "checker": package.checker, "manifest": json.loads(package.manifest_json), "uploaded_at": package.uploaded_at, "time_limit_ms": detail.time_limit_ms, "memory_limit_mb": detail.memory_limit_mb}
    return payload


def _visible_statement(admin: AdminUser):
    if _is_super(admin):
        return select(Problem)
    if admin.role in REVIEWER_ROLES:
        return select(Problem).where((Problem.status == "pending") | (Problem.owner_id == admin.id) | (Problem.created_by == admin.id))
    return select(Problem).where((Problem.owner_id == admin.id) | (Problem.created_by == admin.id))


def _tag_with_descendants(db: Session, tag_id: int) -> set[int]:
    """返回该标签自身及全部后代标签 id（按 parent_id 链向下展开，用于三级知识点筛选）。"""
    ids = {tag_id}
    frontier = [tag_id]
    while frontier:
        children = db.scalars(select(Tag.id).where(Tag.parent_id.in_(frontier))).all()
        frontier = [child_id for child_id in children if child_id not in ids]
        ids.update(frontier)
    return ids


@router.get("/problems")
def list_problems(request: Request, keyword: str = "", type: str = "", difficulty: str = "", source: str = "", knowledge: str = "", owner_id: int | None = Query(default=None, ge=1), status: str = "", page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100), db: Session = Depends(db_session)):
    admin = current_admin(request, db)
    limit(request, "admin-problems-list", client_ip(request), 60, 60)
    stmt = _visible_statement(admin)
    if status: stmt = stmt.where(Problem.status == status)
    if type: stmt = stmt.where(Problem.type == type)
    if difficulty: stmt = stmt.where(Problem.difficulty == difficulty)
    if source: stmt = stmt.where(Problem.source == source)
    if keyword:
        like = f"%{keyword}%"; stmt = stmt.where(Problem.stem.like(like) | Problem.title.like(like) | Problem.problem_id_no.like(like))
    if knowledge:
        # 三级知识点树：按所选节点（阶段/主题/叶子）连同其全部后代叶子过滤；
        # distinct 防止一题命中多个后代标签时在 JOIN 后重复出现。
        knowledge_tag = db.scalar(select(Tag).where(Tag.category == "knowledge", Tag.name == knowledge))
        if knowledge_tag is None:
            stmt = stmt.where(false())
        else:
            tag_ids = _tag_with_descendants(db, knowledge_tag.id)
            stmt = stmt.join(ProblemTag).join(Tag).where(Tag.category == "knowledge", Tag.id.in_(tag_ids)).distinct()
    if owner_id: stmt = stmt.where(Problem.owner_id == owner_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    items = db.scalars(stmt.order_by(Problem.id.desc()).offset((page - 1) * size).limit(size)).all()
    return {"items": [_problem_to_payload(item, db, admin) for item in items], "total": total, "page": page, "size": size}


@router.get("/problem-status-counts")
def problem_status_counts(request: Request, db: Session = Depends(db_session)):
    admin = current_admin(request, db)
    stmt = _visible_statement(admin).subquery()
    counts = {status: 0 for status in ("draft", "pending", "approved")}
    for status, total in db.execute(select(stmt.c.status, func.count()).group_by(stmt.c.status)):
        counts[status] = total
    return {"counts": counts}


@router.get("/problem-owners")
def problem_owners(request: Request, db: Session = Depends(db_session)):
    admin = current_admin(request, db)
    if not _is_super(admin):
        return {"items": [{"id": admin.id, "display_name": admin.display_name}]}
    owners = db.scalars(select(AdminUser).where(AdminUser.status == "active").order_by(AdminUser.display_name, AdminUser.id)).all()
    return {"items": [{"id": item.id, "display_name": item.display_name} for item in owners]}


@router.get("/problems/pickable")
def list_pickable_problems(request: Request, keyword: str = "", type: str = "", difficulty: str = "", knowledge: str = "", sub_type: str = "", page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100), db: Session = Depends(db_session)):
    """组卷选题面板专用：只返回 approved、跨所有负责人，且裁剪掉答案/解析/参考代码。

    题库管理列表的可见范围是"自己负责的题"（_visible_statement），而题库是共享资产：
    审核通过的题谁都能拿来组卷。裁剪答案是因为组卷面板不该把正确选项发进浏览器——
    管理列表的 GET /problems/{id} 是带答案的，选题不能调它。
    """
    current_admin(request, db)
    limit(request, "admin-problems-list", client_ip(request), 60, 60)
    stmt = select(Problem).where(Problem.status == "approved")
    if type: stmt = stmt.where(Problem.type == type)
    if difficulty: stmt = stmt.where(Problem.difficulty == difficulty)
    if sub_type: stmt = stmt.where(Problem.sub_type == sub_type)
    if keyword:
        like = f"%{keyword}%"; stmt = stmt.where(Problem.stem.like(like) | Problem.title.like(like) | Problem.problem_id_no.like(like))
    if knowledge:
        knowledge_tag = db.scalar(select(Tag).where(Tag.category == "knowledge", Tag.name == knowledge))
        if knowledge_tag is None:
            stmt = stmt.where(false())
        else:
            tag_ids = _tag_with_descendants(db, knowledge_tag.id)
            stmt = stmt.join(ProblemTag).join(Tag).where(Tag.category == "knowledge", Tag.id.in_(tag_ids)).distinct()
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    items = db.scalars(stmt.order_by(Problem.id.desc()).offset((page - 1) * size).limit(size)).all()
    return {
        "items": [
            {
                "id": item.id, "problem_id_no": item.problem_id_no, "type": item.type, "sub_type": item.sub_type,
                "title": (item.title or "")[:80],
                "stem_text": _markdown_text(item.stem)[:120],
                "difficulty": item.difficulty, "source": item.source,
                "knowledge": [tag.name for tag in db.scalars(select(Tag).join(ProblemTag, ProblemTag.tag_id == Tag.id).where(ProblemTag.problem_id == item.id, Tag.category == "knowledge"))],
            }
            for item in items
        ],
        "total": total, "page": page, "size": size,
    }


def _analysis_video_status(db: Session, video_id: int | None) -> str | None:
    """解析视频的转码状态（管理端上传卡片展示用）。"""
    if video_id is None:
        return None
    video = db.get(Video, video_id)
    return video.status if video else None


def _validate_analysis_video(db: Session, video_id: int | None) -> int | None:
    """解析视频复用平台视频资产；未转码完成的素材不能被绑定为学生可观看内容。

    与 Scratch 挑战端 `admin_scratch._validate_analysis_video` 同一条口径：除存在性外，
    还要求转码已就绪（status == ready）。此前这里只查存在，会放行仍在上传/转码中的视频，
    形成「配置成功但学生端不可用」的未闭环假象。
    """
    if video_id is None:
        return None
    video = db.get(Video, video_id)
    if video is None:
        raise HTTPException(422, "解析视频不存在。")
    if video.status != "ready":
        raise HTTPException(422, "解析视频尚未转码完成，暂不能绑定。")
    return video.id


@router.post("/problems", status_code=201)
def create_problem(payload: ProblemPayload, request: Request, db: Session = Depends(db_session)):
    require_csrf(request); admin = current_admin(request, db)
    if not _is_editor(admin): _forbid("仅录入员、审核员或超级管理员可创建题目。")
    limit(request, "admin-problems-write", client_ip(request), 60, 60)
    payload.analysis_video_id = _validate_analysis_video(db, payload.analysis_video_id)
    problem = Problem(type=payload.type, sub_type=payload.sub_type if payload.type == "programming" else None, title=(payload.programming.title[:200] if payload.programming else _display_title(payload.type, payload.stem)), stem=payload.stem.strip(), analysis=payload.analysis.strip(), analysis_video_id=payload.analysis_video_id, difficulty=payload.common.difficulty, source=payload.common.source, structure=payload.common.structure, status="draft", created_by=admin.id, owner_id=admin.id, version_no=1, revision=1)
    db.add(problem); db.flush(); problem.root_problem_id = problem.id
    _apply_tags(db, problem.id, payload); _apply_sub_rows(db, problem, payload, payload.type, payload.sub_type)
    _audit_problem(db, request, "problem_create", "draft", admin, problem); db.commit()
    return _problem_to_payload(problem, db, admin)


@router.get("/problems/{problem_id}")
def get_problem(problem_id: int, request: Request, db: Session = Depends(db_session)):
    admin = current_admin(request, db); problem = db.get(Problem, problem_id)
    if not problem: raise HTTPException(404, "题目不存在。")
    if not _can_read(problem, admin): _forbid()
    return _problem_to_payload(problem, db, admin)


@router.put("/problems/{problem_id}")
def update_problem(problem_id: int, payload: ProblemPayload, request: Request, db: Session = Depends(db_session)):
    require_csrf(request); admin = current_admin(request, db); problem = _lock_problem(db, problem_id)
    _require_action(db, problem, admin, "edit"); _require_revision(request, problem)
    previous_type, previous_sub_type = problem.type, problem.sub_type
    problem.type, problem.sub_type = payload.type, payload.sub_type if payload.type == "programming" else None
    problem.stem, problem.analysis = payload.stem.strip(), payload.analysis.strip()
    problem.analysis_video_id = _validate_analysis_video(db, payload.analysis_video_id)
    problem.title = payload.programming.title[:200] if payload.programming else _display_title(payload.type, payload.stem)
    problem.difficulty, problem.source, problem.structure = payload.common.difficulty, payload.common.source, payload.common.structure
    cleanup_dirs = _apply_sub_rows(db, problem, payload, previous_type, previous_sub_type); _apply_tags(db, problem.id, payload); _touch(problem)
    _audit_problem(db, request, "problem_update", "draft", admin, problem, previous_type=previous_type)
    db.commit()
    for storage_dir in cleanup_dirs: _remove_testdata_storage(request.app.state.settings, storage_dir)
    return _problem_to_payload(problem, db, admin)


def _state_action(problem_id: int, request: Request, db: Session, action: str, payload: RejectProblemPayload | None = None):
    require_csrf(request); admin = current_admin(request, db); problem = _lock_problem(db, problem_id)
    _require_action(db, problem, admin, action); _require_revision(request, problem)
    settings = request.app.state.settings
    cleanup_dirs: list[str] = []
    summary: dict = {}
    if action == "submit":
        error = _submission_error(problem, db)
        if error: raise HTTPException(422, error)
        problem.status = "pending"
    elif action == "approve":
        problem.status, problem.reviewed_by, problem.reviewed_at = "approved", admin.id, datetime.now(UTC)
        root_id = problem.root_problem_id or problem.id
        published = db.scalar(select(Problem).where(Problem.id == root_id, Problem.id != problem.id).with_for_update()) if root_id != problem.id else None
        if published is not None:
            # 修订通过：继承线上编号，旧的已发布行退场。组卷引用的 problem_id_no
            # 因此永远指向"当前生效的那一版"，试卷不必跟着题目改版重新组。
            inherited, replaced_id = published.problem_id_no, published.id
            package = db.get(TestDataPackage, published.id)
            if package: cleanup_dirs.append(package.storage_dir)
            # 三步顺序不能换：先摘掉指向旧行的 root_problem_id 外键，再删旧行释放
            # problem_id_no 的唯一约束，最后接管编号。颠倒任意一步都会撞上约束。
            problem.root_problem_id = problem.id
            db.flush()
            db.delete(published); db.flush()
            problem.problem_id_no = inherited
            summary["replaced_problem_id"] = replaced_id
        if not problem.problem_id_no: problem.problem_id_no = f"Q{problem.id:06d}"
    elif action == "reject":
        assert payload is not None
        problem.status, problem.rejected_by, problem.rejected_at, problem.rejection_reason = "draft", admin.id, datetime.now(UTC), payload.reason
    _touch(problem)
    # 自审（审自己录入的题）单独标记，事后可检索出所有未经他人复核的记录。
    if action in {"approve", "reject"} and problem.created_by == admin.id: summary["self_review"] = True
    _audit_problem(db, request, f"problem_{action}", problem.status, admin, problem, **summary)
    db.commit()
    for storage_dir in cleanup_dirs: _remove_testdata_storage(settings, storage_dir)
    return {"message": "操作成功。", "revision": problem.revision, "problem_id_no": problem.problem_id_no}


@router.post("/problems/{problem_id}/submit")
def submit_problem(problem_id: int, request: Request, db: Session = Depends(db_session)):
    return _state_action(problem_id, request, db, "submit")


@router.post("/problems/{problem_id}/approve")
def approve_problem(problem_id: int, request: Request, db: Session = Depends(db_session)):
    return _state_action(problem_id, request, db, "approve")


@router.post("/problems/{problem_id}/reject")
def reject_problem(problem_id: int, payload: RejectProblemPayload, request: Request, db: Session = Depends(db_session)):
    return _state_action(problem_id, request, db, "reject", payload)


@router.delete("/problems/{problem_id}")
def delete_problem(problem_id: int, request: Request, db: Session = Depends(db_session)):
    require_csrf(request); admin = current_admin(request, db); problem = _lock_problem(db, problem_id)
    # 这两条先于权限判定，否则只会回一句泛化的"没有权限"，看不出真正的阻塞原因。
    # root_problem_id 是真实外键：先删已发布行会让在审副本悬空。
    if _open_revision(db, problem) is not None:
        raise HTTPException(409, "该题有修订稿正在审核，请先处理修订稿再删除。")
    blockers = _reference_blockers(db, problem)
    if blockers:
        raise HTTPException(409, "题目已被引用，无法删除：" + "、".join(blockers))
    _require_action(db, problem, admin, "delete"); _require_revision(request, problem)
    package = db.get(TestDataPackage, problem.id); storage_dir = package.storage_dir if package else None
    _audit_problem(db, request, "problem_delete", problem.status, admin, problem); db.delete(problem); db.commit()
    _remove_testdata_storage(request.app.state.settings, storage_dir)
    return {"message": "题目已删除。"}


@router.patch("/problems/{problem_id}/owner")
def transfer_problem_owner(problem_id: int, payload: TransferProblemOwnerPayload, request: Request, db: Session = Depends(db_session)):
    require_csrf(request); admin = current_admin(request, db); problem = _lock_problem(db, problem_id)
    _require_action(db, problem, admin, "transfer_owner"); _require_revision(request, problem)
    owner = db.get(AdminUser, payload.owner_id)
    if not owner or owner.status != "active" or owner.role not in EDITOR_ROLES | REVIEWER_ROLES | {SUPER_ROLE}:
        raise HTTPException(422, "负责人必须是活跃的题库管理员。")
    problem.owner_id = owner.id; _touch(problem); _audit_problem(db, request, "problem_transfer_owner", "success", admin, problem, owner_id=owner.id); db.commit()
    return _problem_to_payload(problem, db, admin)


@router.post("/problems/{problem_id}/revise", status_code=201)
def revise_problem(problem_id: int, request: Request, db: Session = Depends(db_session)):
    """为已发布题目开一份草稿副本；线上内容在副本通过审核前保持不变。"""
    require_csrf(request); admin = current_admin(request, db); source = _lock_problem(db, problem_id)
    _require_action(db, source, admin, "revise"); _require_revision(request, source)
    root_id = source.id  # 副本永远挂在当前已发布行下，链路只有一层
    version_no = (db.scalar(select(func.max(Problem.version_no)).where(Problem.root_problem_id == root_id)) or 0) + 1
    clone = Problem(type=source.type, sub_type=source.sub_type, title=source.title, stem=source.stem, analysis=source.analysis, analysis_video_id=source.analysis_video_id, difficulty=source.difficulty, source=source.source, structure=source.structure, status="draft", root_problem_id=root_id, version_no=version_no, revision=1, created_by=admin.id, owner_id=admin.id)
    db.add(clone); db.flush()
    tag_ids = db.scalars(select(ProblemTag.tag_id).where(ProblemTag.problem_id == source.id)).all()
    for tag_id in tag_ids: db.add(ProblemTag(problem_id=clone.id, tag_id=tag_id))
    for option in db.scalars(select(ChoiceOption).where(ChoiceOption.problem_id == source.id)):
        db.add(ChoiceOption(problem_id=clone.id, option_label=option.option_label, content=option.content, is_correct=option.is_correct, sort_order=option.sort_order))
    for blank in db.scalars(select(FillAnswer).where(FillAnswer.problem_id == source.id)):
        db.add(FillAnswer(problem_id=clone.id, blank_index=blank.blank_index, blank_key=blank.blank_key,
                          answer=blank.answer, alternatives_json=blank.alternatives_json))
    detail = db.get(ProgrammingDetail, source.id)
    copied_dir = None
    if detail:
        db.add(ProgrammingDetail(problem_id=clone.id, input_format=detail.input_format, output_format=detail.output_format, hints=detail.hints, pass_condition=detail.pass_condition, time_limit_ms=detail.time_limit_ms, memory_limit_mb=detail.memory_limit_mb))
        for solution in db.scalars(select(ReferenceSolution).where(ReferenceSolution.problem_id == source.id)):
            db.add(ReferenceSolution(problem_id=clone.id, language=solution.language, code=solution.code))
        package = db.get(TestDataPackage, source.id)
        old_dir, new_dir, new_relative = None, None, None
        if package:
            root = Path(request.app.state.settings.testdata_upload_root).resolve(); old_dir = (root / package.storage_dir).resolve(); new_dir = (root / f"problem_{clone.id}" / uuid4().hex).resolve(); new_relative = new_dir.relative_to(root).as_posix()
            try:
                shutil.copytree(old_dir, new_dir); copied_dir = new_relative
            except OSError as exc:
                db.rollback(); _remove_testdata_storage(request.app.state.settings, new_relative); raise HTTPException(500, "复制测试数据失败。") from exc
            db.add(TestDataPackage(problem_id=clone.id, archive_name=package.archive_name, storage_dir=new_relative, config_yaml=package.config_yaml, manifest_json=package.manifest_json.replace(package.storage_dir, new_relative), checker=package.checker, uploaded_by=admin.id))
        for case in db.scalars(select(TestCase).where(TestCase.problem_id == source.id)):
            input_file = case.input_file.replace(package.storage_dir, new_relative, 1) if package and case.input_file else case.input_file
            output_file = case.output_file.replace(package.storage_dir, new_relative, 1) if package and case.output_file else case.output_file
            db.add(TestCase(problem_id=clone.id, input=case.input, output=case.output, is_sample=case.is_sample, sort_order=case.sort_order, case_no=case.case_no, score=case.score, input_file=input_file, output_file=output_file,
                            time_limit_ms=case.time_limit_ms, memory_limit_mb=case.memory_limit_mb))
    _audit_problem(db, request, "problem_revise", "draft", admin, clone, source_problem_id=source.id)
    try:
        db.commit()
    except Exception:
        db.rollback(); _remove_testdata_storage(request.app.state.settings, copied_dir); raise
    return _problem_to_payload(clone, db, admin)


def _imported_manifest(db: Session, problem_id: int) -> list[dict]:
    """已导入测试点的清单，按 TestCase 行重建。

    清单只是给界面看的投影，判题只认 TestCase。所以任何改了 TestCase 的接口都要
    用它刷一遍 manifest_json，否则界面显示的分值/限制会和真正生效的值对不上。
    """
    rows = db.scalars(
        select(TestCase).where(TestCase.problem_id == problem_id, TestCase.input_file.is_not(None))
        .order_by(TestCase.case_no, TestCase.sort_order)
    ).all()
    return [{"case_no": row.case_no, "input_file": row.input_file, "output_file": row.output_file,
             "score": row.score, "time_limit_ms": row.time_limit_ms, "memory_limit_mb": row.memory_limit_mb}
            for row in rows]


@router.post("/problems/{problem_id}/testdata-zip")
async def upload_cpp_testdata_zip(problem_id: int, request: Request, archive: UploadFile = File(...), db: Session = Depends(db_session)):
    require_csrf(request); admin = current_admin(request, db); limit(request, "admin-problem-testdata-upload", client_ip(request), 12, 300)
    problem = _lock_problem(db, problem_id); _require_action(db, problem, admin, "edit"); _require_revision(request, problem)
    if problem.type != "programming" or problem.sub_type != "cpp": raise HTTPException(400, "仅草稿状态的 C++ 操作题可上传测试数据。")
    filename = (archive.filename or "").strip()
    if not filename.lower().endswith(".zip"): raise HTTPException(400, "请上传 .zip 格式的测试数据包。")
    settings = request.app.state.settings; raw = await archive.read(settings.testdata_zip_max_bytes + 1)
    if len(raw) > settings.testdata_zip_max_bytes: raise HTTPException(413, "ZIP 文件大小超出限制。")
    try: parsed = parse_testdata_zip(raw, max_files=settings.testdata_max_files, max_unpacked_bytes=settings.testdata_unpacked_max_bytes)
    except ValueError as exc: raise HTTPException(400, str(exc)) from exc
    detail = db.get(ProgrammingDetail, problem.id)
    if not detail: raise HTTPException(400, "操作题详情不存在，请先保存题目。")
    root = Path(settings.testdata_upload_root).resolve(); storage_dir = (root / f"problem_{problem.id}" / uuid4().hex).resolve()
    if root not in storage_dir.parents: raise HTTPException(500, "测试数据存储目录配置无效。")
    relative_dir = storage_dir.relative_to(root).as_posix()
    try: write_testdata_files(raw, parsed, storage_dir)
    except OSError as exc: raise HTTPException(500, "测试数据写入失败。") from exc
    old = db.get(TestDataPackage, problem.id); old_dir = old.storage_dir if old else None
    try:
        if parsed.time_limit_ms is not None: detail.time_limit_ms = parsed.time_limit_ms
        if parsed.memory_limit_mb is not None: detail.memory_limit_mb = parsed.memory_limit_mb
        db.execute(delete(TestCase).where(TestCase.problem_id == problem.id, TestCase.input_file.is_not(None)))
        manifest = []
        for order, case in enumerate(parsed.cases):
            input_file, output_file = f"{relative_dir}/{case.case_no}.in", f"{relative_dir}/{case.case_no}.out"; manifest.append({"case_no": case.case_no, "input_file": input_file, "output_file": output_file, "score": case.score, "time_limit_ms": case.time_limit_ms, "memory_limit_mb": case.memory_limit_mb})
            db.add(TestCase(problem_id=problem.id, input="", output="", is_sample=False, sort_order=order, case_no=case.case_no, score=case.score, input_file=input_file, output_file=output_file, time_limit_ms=case.time_limit_ms, memory_limit_mb=case.memory_limit_mb))
        if not old:
            old = TestDataPackage(problem_id=problem.id, archive_name=filename[:255], storage_dir=relative_dir); db.add(old)
        old.archive_name, old.storage_dir, old.config_yaml, old.manifest_json, old.checker, old.uploaded_by = filename[:255], relative_dir, parsed.config_yaml, json.dumps(manifest, ensure_ascii=False), parsed.checker, admin.id
        _touch(problem); _audit_problem(db, request, "problem_testdata_upload", "success", admin, problem, case_count=len(manifest)); db.commit()
    except Exception:
        db.rollback(); _remove_testdata_storage(settings, relative_dir); raise
    if old_dir and old_dir != relative_dir: _remove_testdata_storage(settings, old_dir)
    return {"message": "测试数据导入成功。", "revision": problem.revision, "case_count": len(manifest), "checker": parsed.checker, "time_limit_ms": detail.time_limit_ms, "memory_limit_mb": detail.memory_limit_mb, "manifest": manifest}


def _testdata_dir(settings, package: TestDataPackage) -> Path:
    """把 `storage_dir` 解析成受控根目录下的真实路径。

    上传时已经验过一次，这里**仍然每次都验**：这一层防的不是上传，是"库里的值
    被别的途径改脏"——storage_dir 一旦变成 `../../etc`，下载接口就成了任意文件读取。
    """
    root = Path(settings.testdata_upload_root).resolve()
    target = (root / package.storage_dir).resolve()
    if target != root and root not in target.parents:
        raise HTTPException(500, "测试数据存储目录配置无效。")
    return target


def _readable_problem(request: Request, db: Session, problem_id: int) -> tuple[Problem, AdminUser, TestDataPackage]:
    """下载类接口的共同前置：能读这道题 + 它确实有导入过的测试数据。"""
    admin = current_admin(request, db)
    limit(request, "admin-problem-testdata-download", client_ip(request), 120, 60)
    problem = db.get(Problem, problem_id)
    if not problem:
        raise HTTPException(404, "题目不存在。")
    if not _can_read(problem, admin):
        _forbid()
    package = db.get(TestDataPackage, problem.id)
    if not package:
        raise HTTPException(404, "该题还没有导入测试数据。")
    return problem, admin, package


@router.get("/problems/{problem_id}/testdata/cases/{case_no}")
def download_testdata_case(problem_id: int, case_no: int, request: Request,
                           side: str = Query("in", pattern="^(in|out)$"),
                           db: Session = Depends(db_session)):
    """下载单个测试点的输入或输出文件。

    case_no 不直接拼进路径：先在库里查到这一行，确认它属于这道题且是文件型测试点，
    再按行里的编号取文件。拿路径参数拼文件名是目录穿越最经典的入口。
    """
    problem, admin, package = _readable_problem(request, db, problem_id)
    row = db.scalar(
        select(TestCase).where(TestCase.problem_id == problem.id, TestCase.case_no == case_no,
                               TestCase.input_file.is_not(None))
    )
    if not row:
        raise HTTPException(404, "测试点不存在。")
    path = _testdata_dir(request.app.state.settings, package) / f"{row.case_no}.{side}"
    if not path.is_file():
        raise HTTPException(404, "测试点文件已丢失，请重新上传测试数据。")
    # 判分资产的每一次外流都要留痕，与整卷预览答案同一口径
    _audit_problem(db, request, "problem_testdata_download", "success", admin, problem,
                   case_no=row.case_no, side=side)
    db.commit()
    return FileResponse(path, media_type="text/plain; charset=utf-8",
                        filename=f"{problem.problem_id_no or problem.id}-{row.case_no}.{side}")


@router.get("/problems/{problem_id}/testdata/archive")
def download_testdata_archive(problem_id: int, request: Request, db: Session = Depends(db_session)):
    """把导入的测试数据重新打包下载（N.in / N.out + config.yaml）。

    **是重新打包，不是把当初上传的那个 ZIP 原样吐回来**——原始包不留档（上传时只解出
    数据文件，见 write_testdata_files），而且更重要的是：config.yaml 按**库里现在的值**
    生成，所以在界面上改过分值/限时之后下载，拿到的是改后的配置。下载→改→重新上传
    是闭合的，不会把界面上的改动丢回旧值。
    """
    problem, admin, package = _readable_problem(request, db, problem_id)
    directory = _testdata_dir(request.app.state.settings, package)
    detail = db.get(ProgrammingDetail, problem.id)
    rows = db.scalars(
        select(TestCase).where(TestCase.problem_id == problem.id, TestCase.input_file.is_not(None))
        .order_by(TestCase.case_no)
    ).all()
    if not rows:
        raise HTTPException(404, "该题还没有导入测试数据。")

    config_text = build_config_yaml(
        time_limit_ms=detail.time_limit_ms if detail else 1000,
        memory_limit_mb=detail.memory_limit_mb if detail else 256,
        checker=package.checker,
        cases=[{"case_no": row.case_no, "score": row.score,
                "time_limit_ms": row.time_limit_ms, "memory_limit_mb": row.memory_limit_mb}
               for row in rows],
    )

    # 打进临时文件而不是内存：解包上限默认 128MB，全塞进 BytesIO 会让一次下载
    # 顶掉一大块进程内存。响应发完由 BackgroundTask 删掉。
    handle, temp_name = tempfile.mkstemp(prefix="testdata-", suffix=".zip")
    os.close(handle)
    temp_path = Path(temp_name)
    try:
        with zipfile.ZipFile(temp_path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("config.yaml", config_text)
            for row in rows:
                for side in ("in", "out"):
                    source = directory / f"{row.case_no}.{side}"
                    # 缺文件不整包失败：能下多少是多少，比"什么都拿不到"有用
                    if source.is_file():
                        archive.write(source, f"{row.case_no}.{side}")
    except OSError:
        temp_path.unlink(missing_ok=True)
        raise HTTPException(500, "测试数据打包失败。") from None

    _audit_problem(db, request, "problem_testdata_download", "success", admin, problem,
                   case_count=len(rows), archive=True)
    db.commit()
    return FileResponse(
        temp_path, media_type="application/zip",
        filename=f"{problem.problem_id_no or problem.id}-testdata.zip",
        background=BackgroundTask(lambda: temp_path.unlink(missing_ok=True)),
    )


@router.post("/problems/{problem_id}/unify-testcase-limits")
def unify_testcase_limits(problem_id: int, payload: TestcaseLimitsPayload, request: Request, db: Session = Depends(db_session)):
    """「统一设定」：改题目级限制 + 把所有测试点的逐点值清空回到继承。

    不是把题目级的值复制到每个测试点——复制之后再改题目级就不生效了，而使用者的心智
    一定是"我改了这道题的限制"。清空是唯一能让「统一设定」名副其实的实现（交接文档 §6.4）。
    """
    require_csrf(request)
    admin = current_admin(request, db)
    problem = _lock_problem(db, problem_id)
    _require_action(db, problem, admin, "edit")
    _require_revision(request, problem)
    detail = db.get(ProgrammingDetail, problem.id)
    if not detail:
        raise HTTPException(400, "操作题详情不存在，请先保存题目。")
    detail.time_limit_ms = payload.time_limit_ms
    detail.memory_limit_mb = payload.memory_limit_mb
    db.execute(update(TestCase).where(TestCase.problem_id == problem.id)
               .values(time_limit_ms=None, memory_limit_mb=None))
    # 清单要跟着刷新，否则「已导入测试点」表里还挂着刚被清掉的旧值。
    # 这里直接改清单副本而不是用 _imported_manifest 重建：上面走的是 Core update，
    # session 里的 TestCase 对象还是旧值，重建会把刚清掉的值又写回去。
    package = db.get(TestDataPackage, problem.id)
    if package:
        manifest = json.loads(package.manifest_json)
        for entry in manifest:
            entry["time_limit_ms"], entry["memory_limit_mb"] = None, None
        package.manifest_json = json.dumps(manifest, ensure_ascii=False)
    _touch(problem)
    _audit_problem(db, request, "problem_unify_limits", "success", admin, problem,
                   time_limit_ms=payload.time_limit_ms, memory_limit_mb=payload.memory_limit_mb)
    db.commit()
    return _problem_to_payload(problem, db, admin)


@router.put("/problems/{problem_id}/testdata-cases")
def update_imported_testcases(problem_id: int, payload: ImportedCasesPayload, request: Request, db: Session = Depends(db_session)):
    """已导入测试点的分值 / 限时 / 内存改设。

    ZIP 只负责给测试点的**内容**，这三项在界面上直接改——为了把某个点的分值从 10 调成 20
    就得重新打包上传一次 ZIP，是没有道理的。输入输出不在这个接口里，改它们必须重新上传，
    否则库里的元数据和磁盘上的 .in/.out 会对不上。

    整表提交而不是逐行 PATCH：分值是一组相对权重，逐行存盘时中间状态的总分是错的。
    """
    require_csrf(request)
    admin = current_admin(request, db)
    problem = _lock_problem(db, problem_id)
    _require_action(db, problem, admin, "edit")
    _require_revision(request, problem)
    rows = {row.case_no: row for row in db.scalars(
        select(TestCase).where(TestCase.problem_id == problem.id, TestCase.input_file.is_not(None))
    )}
    if not rows:
        raise HTTPException(400, "该题还没有导入测试数据。")
    # 编号对不上多半是清单过期（别人重传过 ZIP）。静默跳过会让人以为存上了，必须报错。
    unknown = [item.case_no for item in payload.cases if item.case_no not in rows]
    if unknown:
        raise HTTPException(400, f"测试点 {unknown[0]} 不在已导入的测试数据里，请重新加载页面。")
    for item in payload.cases:
        row = rows[item.case_no]
        row.score, row.time_limit_ms, row.memory_limit_mb = item.score, item.time_limit_ms, item.memory_limit_mb
    manifest = _imported_manifest(db, problem.id)
    package = db.get(TestDataPackage, problem.id)
    if package:
        package.manifest_json = json.dumps(manifest, ensure_ascii=False)
    _touch(problem)
    _audit_problem(db, request, "problem_testcase_meta", "success", admin, problem, case_count=len(payload.cases))
    db.commit()
    return {"message": "测试点设置已保存。", "revision": problem.revision, "manifest": manifest}


@router.get("/problems/{problem_id}/audit")
def problem_audit(problem_id: int, request: Request, db: Session = Depends(db_session)):
    admin = current_admin(request, db)
    if not _is_reviewer(admin): _forbid("仅审核员或超级管理员可查看审计记录。")
    events = db.scalars(select(AuditEvent).where(AuditEvent.resource_type == "problem", AuditEvent.resource_id == problem_id).order_by(AuditEvent.id.desc())).all()
    return {"items": [{"event": item.event_type, "outcome": item.outcome, "at": item.created_at, "by": _person_payload(db, item.admin_user_id), "summary": json.loads(item.summary_json) if item.summary_json else {}} for item in events]}


@router.get("/tags")
def list_tags(request: Request, db: Session = Depends(db_session)):
    current_admin(request, db)
    tags = db.scalars(select(Tag).where(Tag.category.in_(TAG_CATEGORIES)).order_by(Tag.category, Tag.name, Tag.id)).all()
    groups = {category: [] for category in TAG_CATEGORIES}
    for tag in tags:
        groups[tag.category].append(
            {"id": tag.id, "name": tag.name, "parent_id": tag.parent_id, "description": tag.description}
        )
    return groups


@router.post("/tags", status_code=201)
def create_tag(payload: CreateTagPayload, request: Request, db: Session = Depends(db_session)):
    require_csrf(request); admin = current_admin(request, db)
    if not _is_super(admin): _forbid("仅超级管理员可维护标签。")
    name = payload.name.strip()
    if not name: raise HTTPException(422, "标签不能为空。")
    if db.scalar(select(Tag).where(Tag.name == name, Tag.category == payload.category)):
        raise HTTPException(409, "同分类标签已存在。")
    parent = None
    if payload.parent_id is not None:
        parent = db.get(Tag, payload.parent_id)
        if parent is None or parent.category != payload.category:
            raise HTTPException(422, "父标签不存在或分类不一致。")
    tag = Tag(
        name=name,
        category=payload.category,
        parent_id=parent.id if parent else None,
        description=payload.description,
        is_system=False,
    )
    db.add(tag)
    audit(db, request.app.state.settings, "problem_tag_create", "success", client_ip(request), admin.id, resource_type="tag", resource_id=None, summary={"category": payload.category, "parent_id": tag.parent_id})
    db.commit(); return {"id": tag.id, "name": tag.name, "category": tag.category, "parent_id": tag.parent_id, "description": tag.description}
