"""后台试卷/组卷：属性配置、题目编排、发布与访问链接生命周期。

骨架严格对齐 admin_questions.py：手工 current_admin、with_for_update 行锁、
If-Match 乐观锁（缺头 428 / 不匹配 409）、中文错误文案、无 relationship() 全显式 select()。
赛制字段（paper_type / ruleset）只记录预设来源，本文件永远不读它们做行为分支。
"""

from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from ..models import (
    AdminUser, AuditEvent, ChoiceOption, ClassGroup, CourseLessonBlock, ExamAssignment,
    ExamLink, FillAnswer, LessonPaperBlock, Paper, PaperAttempt, PaperQuestion, Problem,
    ProgrammingDetail, ReferenceSolution, TestCase, User,
)
from ..permissions import EDITOR_ROLES, REVIEWER_ROLES, SUPER_ROLE
from ..permissions import is_editor as _is_editor
from ..permissions import is_reviewer as _is_reviewer
from ..permissions import is_super as _is_super
from ..schemas import ExamLinkPayload, PaperPayload, TransferPaperOwnerPayload
from ..scoring import parse_blank_alternatives
from .admin_auth import audit, client_ip, current_admin, db_session, limit, require_csrf

router = APIRouter(prefix="/api/admin", tags=["admin-papers"])

EDITABLE_STATUSES = {"draft", "published"}  # 试卷不走审核流，已发布仍可改；归档即锁定
ASSIGNMENT_TARGET_LABELS = {"class": "班级", "student": "学生"}


class ExamAssignmentPayload(BaseModel):
    target_type: str = Field(pattern="^(class|student)$")
    target_id: int = Field(gt=0)


def _forbid(message: str = "没有执行该试卷操作的权限。") -> None:
    raise HTTPException(403, message)


def _can_read(paper: Paper, admin: AdminUser) -> bool:
    if _is_super(admin) or admin.role in REVIEWER_ROLES:
        return True
    return paper.created_by == admin.id or paper.owner_id == admin.id


def _can_edit(paper: Paper, admin: AdminUser) -> bool:
    if paper.status not in EDITABLE_STATUSES:
        return False
    return _is_super(admin) or (admin.role in EDITOR_ROLES and paper.owner_id == admin.id)


def _can_destroy(paper: Paper, admin: AdminUser) -> bool:
    """删除权：与「编辑权」是两个维度，故意不复用 _can_edit()。

    编辑权问的是「内容还能不能改」——归档即锁定，答案是不能。
    删除权问的是「这条记录还要不要留」——归档卷正是最该被清理的那一类。
    已发布卷不在此列：链接还在外面流传，必须先归档（连带停掉全部链接）再删，
    不给「一步销毁」的路径。
    """
    if paper.status not in {"draft", "archived"}:
        return False
    return _is_super(admin) or (admin.role in EDITOR_ROLES and paper.owner_id == admin.id)


def _allowed_actions(paper: Paper, admin: AdminUser) -> list[str]:
    actions = ["view"] if _can_read(paper, admin) else []
    if _can_edit(paper, admin):
        actions += ["edit"]
        if paper.status == "draft":
            actions += ["publish"]
        if paper.status == "published":
            actions += ["archive", "manage_links"]  # 链接只在已发布卷上管理：没内容不该有考试安排
    if _can_destroy(paper, admin):
        actions += ["delete"]           # 草稿与归档卷共用这一条
    if _is_super(admin):
        actions += ["transfer_owner"]   # 归档卷也放行：这是「授予他人删除权」的唯一手段
    return actions


def _require_action(paper: Paper, admin: AdminUser, action: str) -> None:
    if action not in _allowed_actions(paper, admin):
        _forbid()


def _lock_paper(db: Session, paper_id: int) -> Paper:
    paper = db.scalar(select(Paper).where(Paper.id == paper_id).with_for_update())
    if not paper:
        raise HTTPException(404, "试卷不存在。")
    return paper


def _require_revision(request: Request, paper: Paper) -> None:
    raw = (request.headers.get("If-Match") or "").strip().strip('"')
    if not raw:
        raise HTTPException(428, "请携带 If-Match 试卷版本号。")
    try:
        expected = int(raw)
    except ValueError as exc:
        raise HTTPException(400, "If-Match 必须是整数版本号。") from exc
    if expected != paper.revision:
        raise HTTPException(409, {"message": "试卷已被其他人更新，请重新加载后再试。", "revision": paper.revision})


def _touch(paper: Paper) -> None:
    paper.revision += 1


def _person_payload(db: Session, admin_id: int | None) -> dict | None:
    admin = db.get(AdminUser, admin_id) if admin_id else None
    return {"id": admin.id, "display_name": admin.display_name} if admin else None


def _audit_paper(db: Session, request: Request, event: str, outcome: str, admin: AdminUser, paper: Paper, **summary):
    audit(
        db,
        request.app.state.settings,
        event,
        outcome,
        client_ip(request),
        admin.id,
        resource_type="paper",
        resource_id=paper.id,
        summary={"status": paper.status, "revision": paper.revision, **summary},
    )


def _recalc_total(db: Session, paper: Paper) -> None:
    """total_score 是冗余列：任何写 paper_questions 的操作后由服务端重算。"""
    paper.total_score = db.scalar(
        select(func.coalesce(func.sum(PaperQuestion.score), 0)).where(PaperQuestion.paper_id == paper.id)
    ) or 0


def _apply_questions(db: Session, paper: Paper, payload: PaperPayload) -> None:
    """题目清单随 PUT 全量替换，与题库 options/blanks 的做法一致。"""
    db.execute(delete(PaperQuestion).where(PaperQuestion.paper_id == paper.id))
    for item in payload.questions:
        db.add(PaperQuestion(paper_id=paper.id, problem_id_no=item.problem_id_no.strip(), sort_order=item.sort_order, score=item.score))
    db.flush()
    _recalc_total(db, paper)


def _exam_url(settings, link: ExamLink) -> str:
    """学员端完整链接。token 与 paper_id_no 是两个东西：编号顺序可枚举会泄题，token 可重置。"""
    path = f"/exam/{link.access_token}"
    base = (settings.exam_base_url or "").rstrip("/")
    return f"{base}{path}" if base else path


def _mask_exam_url(link: ExamLink) -> str:
    """打码到「能口头核对是哪条」为止，刻意不是可用地址。

    给的是没有管理权、但能读这张卷的人（审核员、卷已转让的原作者）看的。
    他们仍可通过 reveal-url 取到完整地址——那条路每次必写审计，见该端点。
    """
    token = link.access_token
    return f"/exam/{token[:4]}…{token[-4:]}"


def _as_utc(value: datetime) -> datetime:
    """SQLite 的 DateTime(timezone=True) 读回是无时区值（写入时已归一到 UTC），
    直接和 datetime.now(UTC) 比会抛 TypeError；统一按 UTC 解释后再比。

    ⚠️ 这只覆盖 Python 侧比较。list_exam_links 的 phase 过滤是在 SQL 里比的，
    SQLAlchemy 的 SQLite DATETIME 绑定会丢掉 tzinfo 只取字面分量——结果正确
    完全依赖「落库分量恒为 UTC」这条隐性约定（前端 toIso() 永远发 toISOString()
    的 UTC 串，Pydantic 解析后带 tz，SQLite 驱动按 UTC 分量落库）。
    哪天有人改成发 +08:00 带偏移的串，phase 过滤会静默错 8 小时：不报错，
    只是筛出来的行不对。改时间链路时先回来读这段。"""
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _link_phase(link: ExamLink, now: datetime) -> str:
    """运行态：只看时间窗口，不看 status（停用与否是另一个维度，前端显示时才合并）。"""
    if link.open_at and _as_utc(link.open_at) > now:
        return "not_started"
    if link.close_at and _as_utc(link.close_at) <= now:
        return "ended"
    return "running"


def _can_manage_links(paper: Paper, admin: AdminUser) -> bool:
    """链接管理权中与卷状态无关的那一半：超管，或本卷负责人（录入员）。"""
    return _is_super(admin) or (admin.role in EDITOR_ROLES and paper.owner_id == admin.id)


def _link_actions(link: ExamLink, paper: Paper, admin: AdminUser) -> list[str]:
    if not _can_read(paper, admin):
        return []
    if not _can_manage_links(paper, admin):
        # 审核员 / 卷已转让的原作者：能看全部配置，但完整地址要走 reveal-url 取（每次留痕）。
        # copy 与 reveal_url 是互斥的两条路，不要同时给——前端据此决定复制走不走那一次往返。
        return ["view", "reveal_url"]
    actions = ["view", "copy"]
    if paper.status == "published":
        actions += ["edit", "reset_token", "disable" if link.status == "active" else "enable"]
    actions += ["delete"]                   # 归档卷的链接允许清理，删除权与卷的删除权同源
    return actions


def _require_link_manage(paper: Paper, admin: AdminUser, *, need_published: bool = True) -> None:
    """权限与状态分两句话报错：403 说「你不能」，409 说「现在不行」，别混。"""
    if not _can_manage_links(paper, admin):
        _forbid("没有管理该试卷考试链接的权限。")
    if need_published and paper.status != "published":
        raise HTTPException(409, "试卷尚未发布或已归档，其下考试链接不可增改；如需清理，请直接删除链接。")


def _link_payload(link: ExamLink, settings, paper: Paper, admin: AdminUser) -> dict:
    """paper / admin 是必传的：完整地址与动作清单都按「这个人能不能管这条链接」裁剪。

    别把它们改回可选——一个忘了传的调用点会静默降级成「无授权上下文」，
    要么白给地址、要么白扣按钮，而且不报错。
    """
    payload = {
        "id": link.id, "paper_id": link.paper_id, "name": link.name, "status": link.status,
        "open_at": link.open_at, "close_at": link.close_at,
        "duration_minutes": link.duration_minutes, "late_start_policy": link.late_start_policy,
        "attempt_limit": link.attempt_limit, "score_policy": link.score_policy,
        "penalty_minutes": link.penalty_minutes, "feedback_mode": link.feedback_mode,
        "show_analysis": link.show_analysis, "show_score": link.show_score,
        "shuffle_questions": link.shuffle_questions, "shuffle_options": link.shuffle_options,
        # 考前提醒与规则：本期只在后台配置与存储，学员端（M9）消费。
        "notice": link.notice, "notice_ack_required": link.notice_ack_required,
        "entry_open_minutes": link.entry_open_minutes, "remind_minutes": link.remind_minutes,
        "warn_unanswered": link.warn_unanswered,
        "revision": link.revision, "created_at": link.created_at, "updated_at": link.updated_at,
    }
    # 前端不许自己推断按钮与运行态：服务器时钟与权限结论随行下发。
    payload["phase"] = _link_phase(link, datetime.now(UTC))
    payload["allowed_actions"] = _link_actions(link, paper, admin)
    # 有管理权的人，完整地址内联——分发本来就是他们的活，不构成「事件」。
    # 其余人只拿打码串；完整地址走 reveal-url，那条路每次写审计。
    if _can_manage_links(paper, admin):
        payload["exam_url"] = _exam_url(settings, link)
    else:
        payload["exam_url_hint"] = _mask_exam_url(link)
    return payload


def _lock_link(db: Session, link_id: int) -> tuple[ExamLink, Paper]:
    link = db.scalar(select(ExamLink).where(ExamLink.id == link_id).with_for_update())
    if not link:
        raise HTTPException(404, "考试链接不存在。")
    paper = db.get(Paper, link.paper_id)
    if not paper:
        raise HTTPException(404, "试卷不存在。")
    return link, paper


def _apply_link_fields(link: ExamLink, payload: ExamLinkPayload) -> None:
    link.name = payload.name
    link.open_at, link.close_at = payload.open_at, payload.close_at
    link.duration_minutes, link.late_start_policy = payload.duration_minutes, payload.late_start_policy
    link.attempt_limit, link.score_policy = payload.attempt_limit, payload.score_policy
    link.penalty_minutes, link.feedback_mode = payload.penalty_minutes, payload.feedback_mode
    link.show_analysis, link.show_score = payload.show_analysis, payload.show_score
    link.shuffle_questions, link.shuffle_options = payload.shuffle_questions, payload.shuffle_options
    link.notice, link.notice_ack_required = payload.notice, payload.notice_ack_required
    link.entry_open_minutes, link.remind_minutes = payload.entry_open_minutes, payload.remind_minutes
    link.warn_unanswered = payload.warn_unanswered


def _resolve_problems(db: Session, id_nos: list[str]) -> dict[str, Problem]:
    if not id_nos:
        return {}
    problems = db.scalars(select(Problem).where(Problem.problem_id_no.in_(id_nos))).all()
    return {problem.problem_id_no: problem for problem in problems}


def _paper_payload(paper: Paper, db: Session, admin: AdminUser, request: Request, with_questions: bool) -> dict:
    settings = request.app.state.settings
    links = db.scalars(select(ExamLink).where(ExamLink.paper_id == paper.id).order_by(ExamLink.id)).all()
    payload = {
        "id": paper.id, "paper_id_no": paper.paper_id_no, "title": paper.title, "description": paper.description,
        "paper_type": paper.paper_type, "subject": paper.subject, "ruleset": paper.ruleset,
        "score_mode": paper.score_mode, "partial_credit_multi": paper.partial_credit_multi,
        "total_score": paper.total_score, "pass_score": paper.pass_score,
        "status": paper.status, "revision": paper.revision,
        "published_at": paper.published_at, "archived_at": paper.archived_at,
        "created_at": paper.created_at, "updated_at": paper.updated_at,
        "owner": _person_payload(db, paper.owner_id), "created_by": _person_payload(db, paper.created_by),
        "allowed_actions": _allowed_actions(paper, admin),
        # 考试安排在链接层：一张卷可有多条，各自独立的时间/次数/呈现配置。
        "links": [_link_payload(link, settings, paper, admin) for link in links],
        "link_count": len(links),
    }
    if with_questions:
        rows = db.scalars(
            select(PaperQuestion).where(PaperQuestion.paper_id == paper.id).order_by(PaperQuestion.sort_order, PaperQuestion.id)
        ).all()
        resolved = _resolve_problems(db, [row.problem_id_no for row in rows])
        payload["questions"] = [
            {
                "problem_id_no": row.problem_id_no, "sort_order": row.sort_order, "score": row.score,
                "problem": (
                    {
                        "id": problem.id, "type": problem.type, "sub_type": problem.sub_type,
                        "title": (problem.title or "")[:80], "difficulty": problem.difficulty, "status": problem.status,
                    }
                    if (problem := resolved.get(row.problem_id_no)) else None
                ),
            }
            for row in rows
        ]
    return payload


def _publish_error(paper: Paper, db: Session) -> str | None:
    """发布校验清单：仿题库 _submission_error() 的集中式写法，全部通过才允许发布。"""
    rows = db.scalars(select(PaperQuestion).where(PaperQuestion.paper_id == paper.id)).all()
    if not rows:
        return "试卷至少需要一道题才能发布。"
    resolved = _resolve_problems(db, [row.problem_id_no for row in rows])
    broken = sorted({row.problem_id_no for row in rows if (problem := resolved.get(row.problem_id_no)) is None or problem.status != "approved"})
    if broken:
        return "以下题目未通过审核或已被删除，无法发布：" + "、".join(broken)
    if sum(row.score for row in rows) <= 0:
        return "试卷总分必须大于 0。"
    if paper.pass_score is not None and paper.pass_score > paper.total_score:
        return "及格分不能超过试卷总分。"
    # 时间自洽校验已随时间字段迁往链接层，由 ExamLinkPayload 的 model_validator 承担。
    # subject 是软标签，唯一硬校验点：卷内编程题的语言不能与试卷学科冲突。
    if paper.subject in {"cpp", "python"}:
        conflicts = sorted({
            row.problem_id_no
            for row in rows
            if (problem := resolved[row.problem_id_no]).type == "programming" and problem.sub_type and problem.sub_type != paper.subject
        })
        if conflicts:
            return "卷内编程题语言与试卷学科不一致：" + "、".join(conflicts)
    return None


def _visible_statement(admin: AdminUser):
    if _is_super(admin) or admin.role in REVIEWER_ROLES:
        return select(Paper)
    return select(Paper).where((Paper.owner_id == admin.id) | (Paper.created_by == admin.id))


@router.get("/papers")
def list_papers(request: Request, keyword: str = "", paper_type: str = "", subject: str = "", status: str = "", owner_id: int | None = Query(default=None, ge=1), page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100), db: Session = Depends(db_session)):
    admin = current_admin(request, db)
    limit(request, "admin-papers-list", client_ip(request), 60, 60)
    stmt = _visible_statement(admin)
    if status: stmt = stmt.where(Paper.status == status)
    if paper_type: stmt = stmt.where(Paper.paper_type == paper_type)
    if subject: stmt = stmt.where(Paper.subject == subject)
    if keyword:
        like = f"%{keyword}%"; stmt = stmt.where(Paper.title.like(like) | Paper.paper_id_no.like(like))
    if owner_id: stmt = stmt.where(Paper.owner_id == owner_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    items = db.scalars(stmt.order_by(Paper.id.desc()).offset((page - 1) * size).limit(size)).all()
    # 列表带题目数与题型构成（编程/单选/多选/判断/填空计数），供表格「题型构成」列。
    question_rows = db.execute(
        select(PaperQuestion.paper_id, PaperQuestion.problem_id_no, PaperQuestion.score)
        .where(PaperQuestion.paper_id.in_([item.id for item in items] or [0]))
    ).all()
    paper_ids = [item.id for item in items] or [0]
    link_counts: dict[int, int] = {}
    active_link_counts: dict[int, int] = {}
    for paper_id, status, count in db.execute(
        select(ExamLink.paper_id, ExamLink.status, func.count())
        .where(ExamLink.paper_id.in_(paper_ids)).group_by(ExamLink.paper_id, ExamLink.status)
    ):
        link_counts[paper_id] = link_counts.get(paper_id, 0) + count
        if status == "active":
            active_link_counts[paper_id] = active_link_counts.get(paper_id, 0) + count
    resolved = _resolve_problems(db, sorted({row.problem_id_no for row in question_rows}))
    stats: dict[int, dict] = {}
    for row in question_rows:
        entry = stats.setdefault(row.paper_id, {"count": 0, "types": {}})
        entry["count"] += 1
        problem = resolved.get(row.problem_id_no)
        if problem:
            entry["types"][problem.type] = entry["types"].get(problem.type, 0) + 1
    return {
        "items": [
            {
                "id": item.id, "paper_id_no": item.paper_id_no, "title": item.title,
                "paper_type": item.paper_type, "subject": item.subject, "ruleset": item.ruleset,
                "total_score": item.total_score, "pass_score": item.pass_score,
                "status": item.status, "revision": item.revision,
                "owner": _person_payload(db, item.owner_id),
                "allowed_actions": _allowed_actions(item, admin),
                "question_count": stats.get(item.id, {"count": 0})["count"],
                "question_types": stats.get(item.id, {"types": {}})["types"],
                # 时间窗口不再是卷的属性（一卷可有多个窗口），列表改为显示链接数。
                "link_count": link_counts.get(item.id, 0),
                "active_link_count": active_link_counts.get(item.id, 0),
            }
            for item in items
        ],
        "total": total, "page": page, "size": size,
    }


@router.get("/paper-status-counts")
def paper_status_counts(request: Request, db: Session = Depends(db_session)):
    admin = current_admin(request, db)
    stmt = _visible_statement(admin).subquery()
    counts = {status: 0 for status in ("draft", "published", "archived")}
    for status, total in db.execute(select(stmt.c.status, func.count()).group_by(stmt.c.status)):
        counts[status] = total
    return {"counts": counts}


@router.get("/paper-owners")
def paper_owners(request: Request, db: Session = Depends(db_session)):
    admin = current_admin(request, db)
    if not _is_super(admin):
        return {"items": [{"id": admin.id, "display_name": admin.display_name}]}
    owners = db.scalars(select(AdminUser).where(AdminUser.status == "active").order_by(AdminUser.display_name, AdminUser.id)).all()
    return {"items": [{"id": item.id, "display_name": item.display_name} for item in owners]}


@router.post("/papers", status_code=201)
def create_paper(payload: PaperPayload, request: Request, db: Session = Depends(db_session)):
    require_csrf(request); admin = current_admin(request, db)
    if not _is_editor(admin): _forbid("仅录入员或超级管理员可创建试卷。")
    limit(request, "admin-papers-write", client_ip(request), 60, 60)
    paper = Paper(
        title=payload.title.strip(), description=payload.description.strip(),
        paper_type=payload.paper_type, subject=payload.subject, ruleset=payload.ruleset,
        score_mode=payload.score_mode, partial_credit_multi=payload.partial_credit_multi,
        pass_score=payload.pass_score, status="draft", created_by=admin.id, owner_id=admin.id, revision=1,
    )
    db.add(paper); db.flush()
    _apply_questions(db, paper, payload)
    _audit_paper(db, request, "paper_create", "draft", admin, paper)
    db.commit()
    return _paper_payload(paper, db, admin, request, with_questions=True)


@router.get("/papers/{paper_id}")
def get_paper(paper_id: int, request: Request, db: Session = Depends(db_session)):
    admin = current_admin(request, db); paper = db.get(Paper, paper_id)
    if not paper: raise HTTPException(404, "试卷不存在。")
    if not _can_read(paper, admin): _forbid()
    return _paper_payload(paper, db, admin, request, with_questions=True)


@router.put("/papers/{paper_id}")
def update_paper(paper_id: int, payload: PaperPayload, request: Request, db: Session = Depends(db_session)):
    require_csrf(request); admin = current_admin(request, db); paper = _lock_paper(db, paper_id)
    _require_action(paper, admin, "edit"); _require_revision(request, paper)
    limit(request, "admin-papers-write", client_ip(request), 60, 60)
    paper.title, paper.description = payload.title.strip(), payload.description.strip()
    paper.paper_type, paper.subject, paper.ruleset = payload.paper_type, payload.subject, payload.ruleset
    paper.score_mode, paper.partial_credit_multi = payload.score_mode, payload.partial_credit_multi
    paper.pass_score = payload.pass_score
    _apply_questions(db, paper, payload)
    if paper.status == "published":
        # 已发布卷的每次修改都必须仍然过得了发布校验，否则校验形同虚设：
        # 考试链接已流传出去，背后不能被改成空卷/含失效题的卷。
        error = _publish_error(paper, db)
        if error: raise HTTPException(422, error)
    _touch(paper)
    _audit_paper(db, request, "paper_update", paper.status, admin, paper)
    db.commit()
    return _paper_payload(paper, db, admin, request, with_questions=True)


@router.post("/papers/{paper_id}/publish")
def publish_paper(paper_id: int, request: Request, db: Session = Depends(db_session)):
    require_csrf(request); admin = current_admin(request, db); paper = _lock_paper(db, paper_id)
    # 先判权限、再判状态：对已发布卷重复发布是「用错了接口」，不是「没权限」。
    # 两者共用一句 403 会把调用方带沟里——前端组卷弹窗曾因此显示「没有权限」，
    # 而那次请求真正的问题是它压根不该发。归档卷仍由 _can_edit 拦成 403（归档即锁定）。
    _require_action(paper, admin, "edit")
    if paper.status != "draft":
        raise HTTPException(409, "试卷已发布，无需重复发布；直接保存修改即可生效。")
    _require_revision(request, paper)
    limit(request, "admin-papers-write", client_ip(request), 60, 60)
    error = _publish_error(paper, db)
    if error: raise HTTPException(422, error)
    paper.status = "published"
    paper.paper_id_no = f"P{paper.id:06d}"
    paper.published_at = datetime.now(UTC)
    # 不再在这里发 token：链接是独立实体，发布后由管理员按需建一条或多条。
    _touch(paper)
    _audit_paper(db, request, "paper_publish", "published", admin, paper, paper_id_no=paper.paper_id_no)
    db.commit()
    return _paper_payload(paper, db, admin, request, with_questions=True)


@router.post("/papers/{paper_id}/archive")
def archive_paper(paper_id: int, request: Request, db: Session = Depends(db_session)):
    require_csrf(request); admin = current_admin(request, db); paper = _lock_paper(db, paper_id)
    _require_action(paper, admin, "archive"); _require_revision(request, paper)
    # 归档即锁定，语义必须贯穿两层：卷锁了而链接还活着，等于没锁。
    paper.status, paper.archived_at = "archived", datetime.now(UTC)
    disabled = db.execute(
        update(ExamLink).where(ExamLink.paper_id == paper.id, ExamLink.status == "active").values(status="disabled")
    ).rowcount
    _touch(paper)
    _audit_paper(db, request, "paper_archive", "archived", admin, paper, disabled_links=disabled)
    db.commit()
    return _paper_payload(paper, db, admin, request, with_questions=True)


def _paper_delete_blocker(db: Session, paper: Paper) -> str | None:
    """删除前置检查。

    ⚠️ 加下游引用表时必须回到这里补分支，否则删卷会打穿下游：
      - paper_attempts（M9 学员端）：已填，见下。成绩不该随卷一起消失，只能留归档。
      - lesson_paper_blocks（课包内容块-练习/作业投放）：已填，见下。
        被课时块引用的卷不可删，先解绑再删。
    题库模块的 _reference_blockers() 就是先留空壳、后填实的，别再让它变成散落的 TODO。
    """
    attempts = db.scalar(
        select(func.count()).select_from(PaperAttempt).where(PaperAttempt.paper_id == paper.id)
    ) or 0
    if attempts:
        return f"该试卷已有 {attempts} 条作答记录，不能删除；如需下线请归档。"
    refs = db.execute(
        select(CourseLessonBlock.lesson_id, LessonPaperBlock.mode)
        .join(LessonPaperBlock, LessonPaperBlock.block_id == CourseLessonBlock.id)
        .where(LessonPaperBlock.paper_id == paper.id)
    ).all()
    if refs:
        places = "、".join(f"课时{lesson_id}({'练习' if mode == 'practice' else '作业'})" for lesson_id, mode in refs[:5])
        return f"该试卷已被 {len(refs)} 个课时块引用（{places}），请先在课包内容编排中解绑再删除。"
    return None


@router.delete("/papers/{paper_id}")
def delete_paper(paper_id: int, request: Request, db: Session = Depends(db_session)):
    require_csrf(request); admin = current_admin(request, db); paper = _lock_paper(db, paper_id)
    _require_action(paper, admin, "delete"); _require_revision(request, paper)
    blocker = _paper_delete_blocker(db, paper)
    if blocker: raise HTTPException(409, blocker)
    # 归档卷名下的链接会被 CASCADE 一并销毁，数量必须进审计：
    # 事后追查「那条链接怎么没了」时，卷的删除记录是唯一线索。
    link_count = db.scalar(select(func.count()).select_from(ExamLink).where(ExamLink.paper_id == paper.id)) or 0
    _audit_paper(db, request, "paper_delete", paper.status, admin, paper, link_count=link_count)
    db.delete(paper); db.commit()  # CASCADE 清掉 paper_questions 与 exam_links
    return {"message": "试卷已删除。"}


@router.patch("/papers/{paper_id}/owner")
def transfer_paper_owner(paper_id: int, payload: TransferPaperOwnerPayload, request: Request, db: Session = Depends(db_session)):
    require_csrf(request); admin = current_admin(request, db); paper = _lock_paper(db, paper_id)
    _require_action(paper, admin, "transfer_owner"); _require_revision(request, paper)
    owner = db.get(AdminUser, payload.owner_id)
    if not owner or owner.status != "active" or owner.role not in EDITOR_ROLES | REVIEWER_ROLES | {SUPER_ROLE}:
        raise HTTPException(422, "负责人必须是活跃的管理员。")
    paper.owner_id = owner.id; _touch(paper)
    _audit_paper(db, request, "paper_transfer_owner", "success", admin, paper, owner_id=owner.id)
    db.commit()
    return _paper_payload(paper, db, admin, request, with_questions=True)


@router.get("/papers/{paper_id}/audit")
def paper_audit(paper_id: int, request: Request, db: Session = Depends(db_session)):
    admin = current_admin(request, db)
    if not _is_reviewer(admin): _forbid("仅审核员或超级管理员可查看审计记录。")
    events = db.scalars(select(AuditEvent).where(AuditEvent.resource_type == "paper", AuditEvent.resource_id == paper_id).order_by(AuditEvent.id.desc())).all()
    return {"items": [{"event": item.event_type, "outcome": item.outcome, "at": item.created_at, "by": _person_payload(db, item.admin_user_id), "summary": json.loads(item.summary_json) if item.summary_json else {}} for item in events]}


# ==================== 整卷预览（试卷参考视图）====================
# 与选题面板的 /problems/pickable 是两条通道：那条裁剪答案、面向「挑题」；
# 这条按卷授权、可带答案（with_answers=1）、面向「核对与打印」。
# with_answers=1 是本模块唯一越过题库可见范围的口子（能读卷即可读卷内所有题的答案），
# 代价是每次都必须写审计事件 admin_paper_preview_answers。不要把口子扩大到别的接口。


def _preview_question_payload(row: PaperQuestion, problem: Problem | None, db: Session, reveal: bool) -> dict:
    """单题的预览载荷。reveal=False 时，答案相关的键整个不出现（不是给空值）。"""
    if problem is None:
        # 题被删/退审时返回占位项：让老师看见「第 N 题没了」，而不是抛 500 或静默跳过。
        return {"sort_order": row.sort_order, "score": row.score, "problem_id_no": row.problem_id_no, "missing": True}
    payload = {
        "sort_order": row.sort_order, "score": row.score,
        "problem_id_no": row.problem_id_no, "missing": False,
        "type": problem.type, "sub_type": problem.sub_type, "stem": problem.stem,
        # 与 _publish_error 同口径：编号还在但状态已不是 approved 的题，预览要标出来——
        # 发布会拒的卷，预览不能渲染得和正常卷一模一样（当前流程产生不了这种行，这是防御）。
        "approved": problem.status == "approved",
    }
    if reveal:
        payload["difficulty"], payload["source"] = problem.difficulty, problem.source
        payload["analysis"] = problem.analysis

    if problem.type in {"choice", "multi_choice", "judge"}:
        options = db.scalars(
            select(ChoiceOption).where(ChoiceOption.problem_id == problem.id).order_by(ChoiceOption.sort_order)
        ).all()
        payload["options"] = [
            {"label": chr(65 + index), "content": item.content, **({"is_correct": item.is_correct} if reveal else {})}
            for index, item in enumerate(options)
        ]
    elif problem.type == "fill" and reveal:
        payload["blanks"] = [
            # 审卷人要看得见"还接受哪些写法"，否则没法判断这个空是不是问得太开放
            {"blank_index": item.blank_index, "blank_key": item.blank_key, "answer": item.answer,
             "alternatives": parse_blank_alternatives(item.alternatives_json)}
            for item in db.scalars(select(FillAnswer).where(FillAnswer.problem_id == problem.id).order_by(FillAnswer.blank_index))
        ]
    elif problem.type == "programming":
        detail = db.get(ProgrammingDetail, problem.id)
        samples = db.scalars(
            select(TestCase).where(TestCase.problem_id == problem.id, TestCase.is_sample.is_(True)).order_by(TestCase.sort_order)
        ).all()
        programming = {
            "title": problem.title,
            "input_format": detail.input_format if detail else "",
            "output_format": detail.output_format if detail else "",
            "hints": detail.hints if detail else "",
            "time_limit_ms": detail.time_limit_ms if detail else 1000,
            "memory_limit_mb": detail.memory_limit_mb if detail else 256,
            "samples": [{"input": item.input, "output": item.output} for item in samples],
        }
        if reveal:
            code = db.scalar(
                select(ReferenceSolution).where(ReferenceSolution.problem_id == problem.id, ReferenceSolution.language == problem.sub_type)
            )
            programming["pass_condition"] = detail.pass_condition if detail else ""
            programming["ref_code"] = {"language": problem.sub_type, "code": code.code if code else ""}
        payload["programming"] = programming
    return payload


@router.get("/papers/{paper_id}/preview")
def preview_paper(paper_id: int, request: Request, with_answers: int = Query(0, ge=0, le=1), db: Session = Depends(db_session)):
    """整卷预览：卷级组装，答案由 with_answers 与审计双重把关。

    绝不能用 /problems/{id} 拼装——那个接口按题库可见范围授权，
    组卷人拿别人的题会取不到，且一次泄漏全部答案。
    """
    admin = current_admin(request, db)
    limit(request, "admin-papers-list", client_ip(request), 60, 60)
    paper = db.get(Paper, paper_id)
    if not paper:
        raise HTTPException(404, "试卷不存在。")
    if not _can_read(paper, admin):
        _forbid()
    reveal = bool(with_answers)
    rows = db.scalars(
        select(PaperQuestion).where(PaperQuestion.paper_id == paper.id).order_by(PaperQuestion.sort_order, PaperQuestion.id)
    ).all()
    resolved = _resolve_problems(db, [row.problem_id_no for row in rows])
    questions = [_preview_question_payload(row, resolved.get(row.problem_id_no), db, reveal) for row in rows]
    if reveal:
        # 答案外泄路径必须留痕：这是「越过题库可见范围」这个口子的唯一代价。
        audit(
            db, request.app.state.settings,
            "paper_preview_answers", "success", client_ip(request), admin.id,
            resource_type="paper", resource_id=paper.id,
            summary={"question_count": len(rows), "paper_id_no": paper.paper_id_no},
        )
        db.commit()  # db_session 依赖不会自动提交；GET 里不显式 commit 这条审计就丢了
    return {
        "id": paper.id, "paper_id_no": paper.paper_id_no, "title": paper.title,
        "description": paper.description, "paper_type": paper.paper_type,
        "subject": paper.subject, "ruleset": paper.ruleset,
        "total_score": paper.total_score, "pass_score": paper.pass_score,
        "score_mode": paper.score_mode, "partial_credit_multi": paper.partial_credit_multi,
        "status": paper.status, "with_answers": reveal, "questions": questions,
    }


# ==================== 考试链接（场次层）====================
# 一张卷可有多条链接，各自独立配置时间/次数/呈现，并可单独重置或停用。
# 权限与卷状态分两句报错（_require_link_manage）：403 说「你不能」，409 说「现在不行」——
# 这是 publish_paper() 那次线上事故的教训，别再用一句 403 把「卷锁了」报成「人没权限」。


@router.get("/exam-links")
def list_exam_links(
    request: Request, keyword: str = "", paper_id: int | None = Query(default=None, ge=1),
    status: str = "", phase: str = "", owner_id: int | None = Query(default=None, ge=1),
    page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100), db: Session = Depends(db_session),
):
    """跨试卷的链接列表：卷的可见范围就是链接的可见范围，不给链接单独发明一套授权。"""
    admin = current_admin(request, db)
    limit(request, "admin-papers-list", client_ip(request), 60, 60)
    visible = _visible_statement(admin).subquery()
    stmt = select(ExamLink).join(visible, ExamLink.paper_id == visible.c.id)
    if paper_id: stmt = stmt.where(ExamLink.paper_id == paper_id)
    if status: stmt = stmt.where(ExamLink.status == status)
    if owner_id: stmt = stmt.where(visible.c.owner_id == owner_id)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(ExamLink.name.like(like) | visible.c.title.like(like) | visible.c.paper_id_no.like(like))
    now = datetime.now(UTC)
    if phase == "not_started":
        stmt = stmt.where(ExamLink.open_at.is_not(None), ExamLink.open_at > now)
    elif phase == "running":
        stmt = stmt.where(or_(ExamLink.open_at.is_(None), ExamLink.open_at <= now),
                          or_(ExamLink.close_at.is_(None), ExamLink.close_at > now))
    elif phase == "ended":
        stmt = stmt.where(ExamLink.close_at.is_not(None), ExamLink.close_at <= now)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    links = db.scalars(stmt.order_by(ExamLink.id.desc()).offset((page - 1) * size).limit(size)).all()
    # 行载荷 = 完整链接配置（编辑弹窗直接用行数据打开，不再多一次往返）+ 所属卷摘要。
    papers = {paper.id: paper for paper in db.scalars(select(Paper).where(Paper.id.in_([link.paper_id for link in links] or [0])))}
    settings = request.app.state.settings
    return {
        "items": [_link_row_payload(link, papers[link.paper_id], admin, db, settings) for link in links],
        "total": total, "page": page, "size": size,
    }


@router.get("/exam-link-counts")
def exam_link_counts(request: Request, db: Session = Depends(db_session)):
    admin = current_admin(request, db)
    visible = _visible_statement(admin).subquery()
    stmt = select(ExamLink.status, func.count()).join(visible, ExamLink.paper_id == visible.c.id).group_by(ExamLink.status)
    counts = {"active": 0, "disabled": 0}
    for status, total in db.execute(stmt):
        counts[status] = total
    counts["all"] = counts["active"] + counts["disabled"]
    return {"counts": counts}


def _link_row_payload(link: ExamLink, paper: Paper, admin: AdminUser, db: Session, settings) -> dict:
    payload = _link_payload(link, settings, paper, admin)
    payload["paper"] = {
        "id": paper.id, "paper_id_no": paper.paper_id_no, "title": paper.title,
        "paper_type": paper.paper_type, "subject": paper.subject, "status": paper.status,
    }
    payload["owner"] = _person_payload(db, paper.owner_id)
    return payload


def _assignment_target_name(db: Session, target_type: str, target_id: int) -> str | None:
    if target_type == "class":
        row = db.get(ClassGroup, target_id)
        return row.name if row else None
    row = db.get(User, target_id)
    return row.username if row else None


def _assignment_payload(row: ExamAssignment, db: Session) -> dict:
    return {
        "id": row.id,
        "exam_link_id": row.exam_link_id,
        "target_type": row.target_type,
        "target_type_label": ASSIGNMENT_TARGET_LABELS[row.target_type],
        "target_id": row.target_id,
        "target_name": _assignment_target_name(db, row.target_type, row.target_id),
        "status": row.status,
        "assigned_by": row.assigned_by,
        "assigned_at": row.assigned_at,
        "ended_at": row.ended_at,
    }


def _assignment_summary(link_id: int, target_type: str, target_id: int, **extra) -> dict:
    return {
        "schema_version": 1,
        "exam_link_id": link_id,
        "target_type": target_type,
        "target_id": target_id,
        **extra,
    }


def _audit_assignment_failure(
    db: Session,
    request: Request,
    admin: AdminUser,
    event: str,
    link_id: int,
    target_type: str,
    target_id: int,
    *,
    reason_code: str,
) -> None:
    audit(
        db,
        request.app.state.settings,
        event,
        "failure",
        client_ip(request),
        admin.id,
        resource_type="exam_assignment",
        summary=_assignment_summary(
            link_id, target_type, target_id, reason_code=reason_code
        ),
    )
    db.commit()


def _require_assignment_manage(
    db: Session,
    request: Request,
    paper: Paper,
    admin: AdminUser,
    event: str,
    link_id: int,
    target_type: str,
    target_id: int,
) -> None:
    try:
        _require_link_manage(paper, admin)
    except HTTPException as exc:
        if exc.status_code == 403:
            _audit_assignment_failure(
                db,
                request,
                admin,
                event,
                link_id,
                target_type,
                target_id,
                reason_code="forbidden",
            )
        raise


def _assignment_target_exists(db: Session, target_type: str, target_id: int) -> bool:
    model = ClassGroup if target_type == "class" else User
    return db.get(model, target_id) is not None


@router.get("/exam-links/{link_id}/assignments")
def list_exam_assignments(
    link_id: int,
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(db_session),
):
    admin = current_admin(request, db)
    link, paper = _lock_link(db, link_id)
    _require_link_manage(paper, admin)
    statement = select(ExamAssignment).where(
        ExamAssignment.exam_link_id == link.id,
        ExamAssignment.status == "active",
    )
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    rows = db.scalars(
        statement.order_by(ExamAssignment.id).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {
        "items": [_assignment_payload(row, db) for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "target_type_options": [
            {"value": value, "label": label}
            for value, label in ASSIGNMENT_TARGET_LABELS.items()
        ],
    }


@router.post("/exam-links/{link_id}/assignments", status_code=201)
def create_exam_assignment(
    link_id: int,
    payload: ExamAssignmentPayload,
    request: Request,
    db: Session = Depends(db_session),
):
    require_csrf(request)
    admin = current_admin(request, db)
    link, paper = _lock_link(db, link_id)
    _require_assignment_manage(
        db, request, paper, admin, "exam_assign", link.id, payload.target_type, payload.target_id
    )
    if not _assignment_target_exists(db, payload.target_type, payload.target_id):
        raise HTTPException(404, "指派目标不存在。")
    existing = db.scalar(
        select(ExamAssignment.id).where(
            ExamAssignment.exam_link_id == link.id,
            ExamAssignment.target_type == payload.target_type,
            ExamAssignment.target_id == payload.target_id,
            ExamAssignment.status == "active",
        )
    )
    if existing is not None:
        _audit_assignment_failure(
            db,
            request,
            admin,
            "exam_assign",
            link.id,
            payload.target_type,
            payload.target_id,
            reason_code="conflict",
        )
        raise HTTPException(409, "该目标已在当前考试名单中。")
    row = ExamAssignment(
        exam_link_id=link.id,
        target_type=payload.target_type,
        target_id=payload.target_id,
        assigned_by=admin.id,
        assigned_at=datetime.now(UTC),
        status="active",
    )
    db.add(row)
    db.flush()
    audit(
        db,
        request.app.state.settings,
        "exam_assign",
        "success",
        client_ip(request),
        admin.id,
        resource_type="exam_assignment",
        resource_id=row.id,
        summary=_assignment_summary(link.id, row.target_type, row.target_id),
    )
    db.commit()
    db.refresh(row)
    return _assignment_payload(row, db)


@router.delete("/exam-links/{link_id}/assignments/{assignment_id}")
def end_exam_assignment(
    link_id: int,
    assignment_id: int,
    request: Request,
    db: Session = Depends(db_session),
):
    require_csrf(request)
    admin = current_admin(request, db)
    link, paper = _lock_link(db, link_id)
    row = db.scalar(
        select(ExamAssignment).where(
            ExamAssignment.id == assignment_id,
            ExamAssignment.exam_link_id == link.id,
        ).with_for_update()
    )
    if row is None:
        raise HTTPException(404, "考试名单记录不存在。")
    _require_assignment_manage(
        db, request, paper, admin, "exam_unassign", link.id, row.target_type, row.target_id
    )
    if row.status != "active":
        _audit_assignment_failure(
            db,
            request,
            admin,
            "exam_unassign",
            link.id,
            row.target_type,
            row.target_id,
            reason_code="conflict",
        )
        raise HTTPException(409, "该考试名单记录已经取消。")
    row.status = "ended"
    row.ended_at = datetime.now(UTC)
    audit(
        db,
        request.app.state.settings,
        "exam_unassign",
        "success",
        client_ip(request),
        admin.id,
        resource_type="exam_assignment",
        resource_id=row.id,
        summary=_assignment_summary(
            link.id,
            row.target_type,
            row.target_id,
            old_status="active",
            new_status="ended",
        ),
    )
    db.commit()
    db.refresh(row)
    return _assignment_payload(row, db)


@router.get("/papers/{paper_id}/links")
def list_paper_links(paper_id: int, request: Request, db: Session = Depends(db_session)):
    admin = current_admin(request, db); paper = db.get(Paper, paper_id)
    if not paper: raise HTTPException(404, "试卷不存在。")
    if not _can_read(paper, admin): _forbid()
    links = db.scalars(select(ExamLink).where(ExamLink.paper_id == paper_id).order_by(ExamLink.id)).all()
    settings = request.app.state.settings
    return {"items": [_link_payload(link, settings, paper, admin) for link in links], "paper_status": paper.status}


@router.post("/papers/{paper_id}/links", status_code=201)
def create_paper_link(paper_id: int, payload: ExamLinkPayload, request: Request, db: Session = Depends(db_session)):
    require_csrf(request); admin = current_admin(request, db); paper = _lock_paper(db, paper_id)
    _require_link_manage(paper, admin)
    limit(request, "admin-papers-write", client_ip(request), 60, 60)
    if db.scalar(select(ExamLink.id).where(ExamLink.paper_id == paper_id, ExamLink.name == payload.name)):
        raise HTTPException(409, "同一张试卷内的链接名称不能重复。")
    link = ExamLink(paper_id=paper.id, access_token=secrets.token_hex(16), status="active", created_by=admin.id, revision=1)
    _apply_link_fields(link, payload)
    db.add(link); db.flush()
    _audit_paper(db, request, "paper_link_create", "active", admin, paper, link_id=link.id, link_name=link.name)
    db.commit()
    return _link_payload(link, request.app.state.settings, paper, admin)


@router.put("/links/{link_id}")
def update_paper_link(link_id: int, payload: ExamLinkPayload, request: Request, db: Session = Depends(db_session)):
    require_csrf(request); admin = current_admin(request, db); link, paper = _lock_link(db, link_id)
    _require_link_manage(paper, admin); _require_revision(request, link)
    limit(request, "admin-papers-write", client_ip(request), 60, 60)
    clash = db.scalar(select(ExamLink.id).where(ExamLink.paper_id == link.paper_id, ExamLink.name == payload.name, ExamLink.id != link.id))
    if clash: raise HTTPException(409, "同一张试卷内的链接名称不能重复。")
    _apply_link_fields(link, payload); link.revision += 1
    _audit_paper(db, request, "paper_link_update", link.status, admin, paper, link_id=link.id, link_name=link.name)
    db.commit()
    return _link_payload(link, request.app.state.settings, paper, admin)


@router.post("/links/{link_id}/reset-token")
def reset_link_token(link_id: int, request: Request, db: Session = Depends(db_session)):
    """只重置这一条：链接泄露时的止血动作不该波及同卷的其他场次。"""
    require_csrf(request); admin = current_admin(request, db); link, paper = _lock_link(db, link_id)
    _require_link_manage(paper, admin); _require_revision(request, link)
    link.access_token = secrets.token_hex(16); link.revision += 1
    _audit_paper(db, request, "paper_link_reset_token", "success", admin, paper, link_id=link.id, link_name=link.name)
    db.commit()
    return _link_payload(link, request.app.state.settings, paper, admin)


@router.post("/links/{link_id}/disable")
def disable_link(link_id: int, request: Request, db: Session = Depends(db_session)):
    """停用而非删除：作答记录要保留归属，链接本身留痕。"""
    require_csrf(request); admin = current_admin(request, db); link, paper = _lock_link(db, link_id)
    _require_link_manage(paper, admin); _require_revision(request, link)
    if link.status == "disabled":
        raise HTTPException(409, "链接已经是停用状态。")
    link.status = "disabled"; link.revision += 1
    _audit_paper(db, request, "paper_link_disable", "disabled", admin, paper, link_id=link.id, link_name=link.name)
    db.commit()
    return _link_payload(link, request.app.state.settings, paper, admin)


@router.post("/links/{link_id}/enable")
def enable_link(link_id: int, request: Request, db: Session = Depends(db_session)):
    """停用的反向操作。归档卷的链接走不到这里——_require_link_manage 会以 409 说明原因。"""
    require_csrf(request); admin = current_admin(request, db); link, paper = _lock_link(db, link_id)
    _require_link_manage(paper, admin); _require_revision(request, link)
    if link.status == "active":
        raise HTTPException(409, "链接已经是启用状态。")
    link.status = "active"; link.revision += 1
    _audit_paper(db, request, "paper_link_enable", "active", admin, paper, link_id=link.id, link_name=link.name)
    db.commit()
    return _link_payload(link, request.app.state.settings, paper, admin)


@router.delete("/links/{link_id}")
def delete_link(link_id: int, request: Request, db: Session = Depends(db_session)):
    require_csrf(request); admin = current_admin(request, db); link, paper = _lock_link(db, link_id)
    # 归档卷的链接允许清理（need_published=False）：删除权与卷的删除权同源。
    _require_link_manage(paper, admin, need_published=False); _require_revision(request, link)
    # paper_attempts.exam_link_id 是 CASCADE：有作答记录的链接一删，成绩、代码提交、
    # 判题明细会静默全没，而且这是唯一能绕过 _paper_delete_blocker 销毁成绩的路径。
    # 口径与删卷一致：成绩不该随链接一起消失，只能停用。
    attempts = db.scalar(
        select(func.count()).select_from(PaperAttempt).where(PaperAttempt.exam_link_id == link.id)
    ) or 0
    if attempts:
        raise HTTPException(409, f"该链接已有 {attempts} 条作答记录，不能删除；如需下线请停用。")
    _audit_paper(db, request, "paper_link_delete", link.status, admin, paper, link_id=link.id, link_name=link.name)
    db.delete(link); db.commit()
    return {"message": "考试链接已删除。"}


@router.post("/links/{link_id}/reveal-url")
def reveal_link_url(link_id: int, request: Request, db: Session = Depends(db_session)):
    """没有管理权的人取用完整考试地址的唯一通道，每次必写审计。

    为什么不在列表接口里记：GET /papers/{id} 在前端每次点归档/删除/发布的确认框之前
    都会调一次，GET /exam-links 每翻一页调一次——按读取记，审计表会被自己人的正常操作
    淹掉，而且记的是「看了列表」，看 ≠ 发出去。这里复刻 preview_paper 的 with_answers=1：
    把越界取用做成一个显式动作，审计条数 = 实际取用次数，精确回答「地址是谁拿走的」。

    有管理权的人不走这条路——他们的完整地址内联在列表里。这个不对称是有意的：
    负责人持有地址是基线，不是事件。summary 里仍记 by_manager，便于事后统计口径。

    POST 而非 GET：有副作用的读取不该被浏览器预取或缓存。
    """
    require_csrf(request); admin = current_admin(request, db)
    link, paper = _lock_link(db, link_id)
    if not _can_read(paper, admin):
        _forbid("没有查看该试卷考试链接的权限。")
    limit(request, "admin-papers-list", client_ip(request), 60, 60)
    _audit_paper(
        db, request, "paper_link_reveal_url", "success", admin, paper,
        link_id=link.id, link_name=link.name, by_manager=_can_manage_links(paper, admin),
    )
    db.commit()  # db_session 依赖不自动提交；不显式 commit 这条审计就丢了（同 preview_paper）
    return {"exam_url": _exam_url(request.app.state.settings, link)}
