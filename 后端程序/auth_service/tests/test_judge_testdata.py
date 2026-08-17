"""ZIP 导入的测试点必须真的进入判题。

回归的缺陷：`upload_cpp_testdata_zip()` 把测试点内容写在磁盘上，`input`/`output`
两列留空串；而 `_judge_inputs()` 曾经直接读这两列。结果是**所有隐藏测试点都变成
「空输入 → 期望空输出」**——不输出任何东西的程序满分，正确解法 0 分，判分与正确性
负相关。它一直没暴露，只因为默认判题后端是 FakeJudgeClient（按代码里的魔法串出结论，
不比对输出），切到 go-judge 才会炸。

本文件单独成文件而不是并进 test_exam.py：它测的是「题库存的数据 → 判题吃到的数据」
这条纵向链路，与作答闭环是两件事。
"""

import zipfile
from io import BytesIO
from types import SimpleNamespace

import pytest
from test_exam import (
    _token_of,
    admin_login,
    build_app,
    common,
    link_payload,
    match,
    scsrf,
    student_login,
)

from app.models import CodeSubmission
from app.oj_testdata import JudgeDataUnavailable, read_case_content
from app.routers.exam import _judge_inputs

# 断言目标：这两组内容必须原样出现在送去判题的 JudgeCase 里。
ZIP_CASES = (("7 8\n", "15\n"), ("100 1\n", "101\n"))


def zip_bytes() -> bytes:
    with BytesIO() as stream:
        with zipfile.ZipFile(stream, "w") as archive:
            for case_no, (data_in, data_out) in enumerate(ZIP_CASES, start=1):
                archive.writestr(f"{case_no}.in", data_in)
                archive.writestr(f"{case_no}.out", data_out)
            archive.writestr(
                "config.yaml",
                "time_limit: 1s\nmemory_limit: 256mb\ncases:\n  1: {score: 40}\n  2: {score: 60}\n",
            )
        return stream.getvalue()


def cpp_payload() -> dict:
    """pass_condition 取「编译通过」：本用例要验的是判题读到什么，
    不想被「全测试点通过必须上传 ZIP」的提交校验牵着走（ZIP 照传不误）。"""
    return {
        "type": "programming", "sub_type": "cpp",
        "common": common(difficulty="普及-", source="洛谷"),
        "stem": "输入两个整数，输出和。", "analysis": "", "options": [], "blanks": [],
        "programming": {
            "title": "A+B", "pass_condition": "编译通过",
            "input_format": "两个整数", "output_format": "一个整数", "hints": "无",
            "samples": [{"input": "1 2", "output": "3"}],
            "ref_code": {"cpp": "int main(){}", "python": ""},
            "manual_test_cases": [],
        },
    }


def test_zip_testcases_reach_the_judge(tmp_path):
    app = build_app(tmp_path)
    admin, headers = admin_login(app)

    created = admin.post("/api/admin/problems", headers=headers, json=cpp_payload())
    assert created.status_code == 201, created.text
    problem_id = created.json()["id"]

    uploaded = admin.post(
        f"/api/admin/problems/{problem_id}/testdata-zip", headers=match(headers, 1),
        files={"archive": ("ab.zip", zip_bytes(), "application/zip")},
    )
    assert uploaded.status_code == 200, uploaded.text
    revision = uploaded.json()["revision"]
    assert admin.post(f"/api/admin/problems/{problem_id}/submit",
                      headers=match(headers, revision)).status_code == 200
    assert admin.post(f"/api/admin/problems/{problem_id}/approve",
                      headers=match(headers, revision + 1)).status_code == 200
    id_no = admin.get(f"/api/admin/problems/{problem_id}", headers=headers).json()["problem_id_no"]

    paper = admin.post("/api/admin/papers", headers=headers, json={
        "title": "ZIP 判题卷", "description": "", "paper_type": "测试卷", "subject": "cpp",
        "ruleset": "IOI", "score_mode": "testcase", "partial_credit_multi": False, "pass_score": None,
        "questions": [{"problem_id_no": id_no, "score": 100, "sort_order": 0}],
    })
    assert paper.status_code == 201, paper.text
    paper_id = paper.json()["id"]
    assert admin.post(f"/api/admin/papers/{paper_id}/publish",
                      headers=match(headers, 1)).status_code == 200
    link = admin.post(f"/api/admin/papers/{paper_id}/links", headers=headers, json=link_payload())
    assert link.status_code == 201, link.text

    student = student_login(app)
    token = _token_of(app, link.json()["id"])
    started = student.post(f"/api/exam/{token}/start", headers=scsrf(student))
    assert started.status_code == 201, started.text
    attempt_id = started.json()["attempt_id"]
    posted = student.post(
        f"/api/exam/attempts/{attempt_id}/code", headers=scsrf(student),
        json={"problem_id_no": id_no, "language": "cpp", "code": "int main(){}", "kind": "submit"},
    )
    assert posted.status_code == 200, posted.text

    db = app.state.session_factory()
    try:
        submission = db.get(CodeSubmission, posted.json()["id"])
        inputs = _judge_inputs(db, submission, None, app.state.settings)
    finally:
        db.close()

    hidden = [case for case in inputs["cases"] if not case.is_sample]
    assert [case.input for case in hidden] == [data_in for data_in, _ in ZIP_CASES]
    assert [case.expected for case in hidden] == [data_out for _, data_out in ZIP_CASES]
    # 逐点分值也必须跟着 config.yaml 走，否则 testcase 模式的折算是错的
    assert [case.weight for case in hidden] == [40, 60]
    # 样例仍然走库里的两列，不受本次改动影响
    samples = [case for case in inputs["cases"] if case.is_sample]
    assert [(case.input, case.expected) for case in samples] == [("1 2", "3")]


def _settings(tmp_path, max_bytes: int = 1024):
    return SimpleNamespace(testdata_upload_root=str(tmp_path), judge_case_max_bytes=max_bytes)


def _case(**overrides):
    row = {"input": "", "output": "", "input_file": None, "output_file": None}
    row.update(overrides)
    return SimpleNamespace(**row)


def test_missing_file_raises_instead_of_judging_empty(tmp_path):
    """文件丢了必须抛。当成空串继续判，就退回本文件开头描述的那个缺陷，且这次无声。"""
    with pytest.raises(JudgeDataUnavailable):
        read_case_content(_settings(tmp_path),
                          _case(input_file="problem_1/x/1.in", output_file="problem_1/x/1.out"))


def test_path_escape_is_rejected(tmp_path):
    """storage_dir 来自数据库不是用户输入，但一次写错的迁移就能让它指向根目录外，
    而这里读到的东西会原样当 stdin 送进沙箱。"""
    outside = tmp_path.parent / "outside.in"
    outside.write_text("secret", encoding="utf-8")
    with pytest.raises(JudgeDataUnavailable):
        read_case_content(_settings(tmp_path),
                          _case(input_file="../outside.in", output_file="../outside.in"))


def test_oversized_case_is_rejected(tmp_path):
    """单点体积上限。先看 stat 再读，别让一个超大 .in 先把进程撑死再报错。"""
    (tmp_path / "big.in").write_text("x" * 4096, encoding="utf-8")
    (tmp_path / "big.out").write_text("y", encoding="utf-8")
    with pytest.raises(JudgeDataUnavailable):
        read_case_content(_settings(tmp_path, max_bytes=1024),
                          _case(input_file="big.in", output_file="big.out"))


def test_inline_cases_are_untouched(tmp_path):
    """手工录入的点（Python 隐藏点）内容在库里、没有文件，必须原样返回。
    判断依据是 input_file 而不是 is_sample——手工点也不是样例。"""
    assert read_case_content(_settings(tmp_path), _case(input="1 2", output="3")) == ("1 2", "3")
