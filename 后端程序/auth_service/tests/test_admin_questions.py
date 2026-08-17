import zipfile
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from test_admin_courses import add_section, create_category, create_course
from app.config import DEV_FERNET_KEY, Settings
from app.database import build_database
from app.main import create_app
from app.models import AdminUser, Base, Tag
from app.models import TestCase as CaseRow
from app.oj_testdata import parse_testdata_zip
from app.routers.admin_questions import _markdown_text
from app.security import password_hash

PASSWORD = "Admin-pass-123!"


def admin_client(tmp_path: Path) -> TestClient:
    settings = Settings(
        environment="test", database_url=f"sqlite:///{tmp_path / 'qb_test.db'}",
        outbox_encryption_key=DEV_FERNET_KEY, cookie_secure=False, smtp_host=None,
        smtp_username=None, smtp_password=None, smtp_from=None, captcha_enabled=False,
        redis_url=None,
        mfa_enabled=False, pwned_check_enabled=False, slider_captcha_enabled=False,
        testdata_upload_root=str(tmp_path / "testdata"),
    )
    engine, _ = build_database(settings.database_url)
    Base.metadata.create_all(engine); engine.dispose()
    client = TestClient(create_app(settings))
    db = client.app.state.session_factory()
    try:
        for username, role in (("root", "super_admin"), ("writer", "editor"), ("writer2", "editor"), ("reviewer", "reviewer")):
            db.add(AdminUser(username=username, password_hash=password_hash.hash(PASSWORD), display_name=username, role=role))
        for category, name in (("knowledge", "网络"), ("knowledge", "模拟"), ("stage", "C++基础"), ("business", "内部练习")):
            db.add(Tag(name=name, category=category, is_system=True))
        db.commit()
    finally:
        db.close()
    return client


def login(client: TestClient, username: str = "root") -> dict[str, str]:
    client.get("/api/admin/csrf")
    response = client.post("/api/admin/login", headers={"X-CSRF-Token": client.cookies.get("admin_csrf_token")}, json={"username": username, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"X-CSRF-Token": client.cookies.get("admin_csrf_token")}


def match(headers: dict[str, str], revision: int) -> dict[str, str]:
    return {**headers, "If-Match": str(revision)}


def choice_payload() -> dict:
    return {"type": "choice", "sub_type": None, "common": {"difficulty": "入门", "source": "自命题", "structure": "单项知识点", "knowledge": ["网络"], "stage": [], "business": []}, "stem": "## 传输层\n\nTCP 是**面向连接**的协议？", "analysis": "解析：见 `RFC 793`。", "options": [{"content": "对", "is_correct": True}, {"content": "错", "is_correct": False}], "blanks": [], "programming": None}


def programming_payload(language: str = "cpp", condition: str = "全测试点通过") -> dict:
    return {"type": "programming", "sub_type": language, "common": {"difficulty": "普及-", "source": "洛谷", "structure": "综合应用", "knowledge": ["模拟"], "stage": ["C++基础"], "business": []}, "stem": "输入两个整数，输出和。", "analysis": "", "options": [], "blanks": [], "programming": {"title": "A+B Problem", "pass_condition": condition, "input_format": "两个整数 $a, b$（$1 \\le a, b \\le 10^9$）", "output_format": "一个整数", "hints": "无", "samples": [{"input": "1 2", "output": "3"}], "ref_code": {"cpp": "int main(){}", "python": "print(1)"}, "manual_test_cases": [] if language == "cpp" else [{"input": "-1 1", "output": "0"}]}}


def zip_testdata() -> bytes:
    with BytesIO() as stream:
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("1.in", "1 2\n"); archive.writestr("1.out", "3\n")
            archive.writestr("config.yaml", "time_limit: 2s\nmemory_limit: 256mb\ncases:\n  1: {score: 100}\n")
        return stream.getvalue()


def test_cpp_edit_preserves_samples_and_zip_limits(tmp_path):
    with admin_client(tmp_path) as client:
        headers = login(client)
        created = client.post("/api/admin/problems", headers=headers, json=programming_payload()).json()
        assert created["revision"] == 1
        uploaded = client.post(f"/api/admin/problems/{created['id']}/testdata-zip", headers=match(headers, 1), files={"archive": ("ab.zip", zip_testdata(), "application/zip")})
        assert uploaded.status_code == 200, uploaded.text
        assert uploaded.json()["time_limit_ms"] == 2000
        old_file = tmp_path / "testdata" / uploaded.json()["manifest"][0]["input_file"]
        assert old_file.exists()
        replaced = client.post(f"/api/admin/problems/{created['id']}/testdata-zip", headers=match(headers, 2), files={"archive": ("ab-v2.zip", zip_testdata(), "application/zip")})
        assert replaced.status_code == 200, replaced.text
        assert not old_file.exists()
        payload = programming_payload(); payload["programming"]["title"] = "A+B V2"
        # ZIP 的 config.yaml 覆盖了题目级限制（2s），前端上传后会回填表单再保存（交接文档 §6.1）
        payload["programming"]["time_limit_ms"] = 2000
        payload["programming"]["memory_limit_mb"] = 256
        updated = client.put(f"/api/admin/problems/{created['id']}", headers=match(headers, 3), json=payload)
        assert updated.status_code == 200, updated.text
        detail = updated.json()["programming"]
        assert detail["title"] == "A+B V2"
        assert detail["samples"][0]["input"] == "1 2" and detail["samples"][0]["output"] == "3"
        assert detail["testdata_package"]["time_limit_ms"] == 2000
        # Markdown 源码原样存取：服务端不再做 HTML 净化，`\le`、`$` 这些标记必须逐字返回。
        assert detail["input_format"] == payload["programming"]["input_format"]


def test_server_rejects_mixed_payload_unknown_tags_and_stale_revision(tmp_path):
    with admin_client(tmp_path) as client:
        headers = login(client)
        bad = choice_payload(); bad["programming"] = programming_payload()["programming"]
        assert client.post("/api/admin/problems", headers=headers, json=bad).status_code == 422
        unknown = choice_payload(); unknown["common"]["knowledge"] = ["不存在"]
        assert client.post("/api/admin/problems", headers=headers, json=unknown).status_code == 422
        created = client.post("/api/admin/problems", headers=headers, json=choice_payload()).json()
        assert client.put(f"/api/admin/problems/{created['id']}", headers=match(headers, 99), json=choice_payload()).status_code == 409
        assert client.put(f"/api/admin/problems/{created['id']}", headers=headers, json=choice_payload()).status_code == 428


def test_markdown_stem_survives_round_trip(tmp_path):
    """题干存 Markdown 源码，服务端一个字都不改。

    以前 stem 存净化后的 HTML：`<` 被转义、非白名单标签被丢弃，
    题面里的 `#include <iostream>` 和 `vector<int>` 因此活不下来。
    """
    with admin_client(tmp_path) as client:
        headers = login(client)
        stem = "## 数组求和\n\n用 `vector<int>` 存数据：\n\n```cpp\n#include <iostream>\nint a[10];\n```"
        payload = choice_payload(); payload["stem"] = stem
        payload["options"] = [{"content": "$O(n)$", "is_correct": True}, {"content": "$O(n^2)$", "is_correct": False}]
        created = client.post("/api/admin/problems", headers=headers, json=payload)
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["stem"] == stem
        assert body["options"][0]["content"] == "$O(n)$"
        reloaded = client.get(f"/api/admin/problems/{body['id']}", headers=headers).json()
        assert reloaded["stem"] == stem


def test_markdown_text_strips_markup_but_keeps_code_body():
    """标题派生和判空走 _markdown_text：剥标记、留正文。"""
    assert _markdown_text("## 数组求和\n\n用 `vector<int>` 存数据") == "数组求和 用 vector<int> 存数据"
    assert _markdown_text("见 [文档](https://example.com/doc) 第 2 节") == "见 文档 第 2 节"
    assert _markdown_text("![配图](/img/a.png)\n\n**加粗**与*斜体*") == "加粗与斜体"
    assert _markdown_text("```cpp\n#include <iostream>\n```") == "#include <iostream>"
    assert _markdown_text("> 提示\n\n- 第一项\n- 第二项\n\n1. 甲\n2. 乙") == "提示 第一项 第二项 甲 乙"
    assert _markdown_text("| a | b |\n| --- | --- |\n| 1 | 2 |") == "a b 1 2"
    # 填空占位符是空位标记而不是正文，派生标题时要去掉。
    assert _markdown_text("圆周率约等于 \\placeholder[blank_1]{} 。") == "圆周率约等于 。"
    # 只有标记没有正文，等价于空题干——判空必须能识别出来。
    assert _markdown_text("###   \n\n---\n") == ""
    assert _markdown_text("") == "" and _markdown_text(None) == ""


def test_editor_isolated_and_revision_inherits_problem_id_no(tmp_path):
    with admin_client(tmp_path) as client:
        writer_headers = login(client, "writer")
        created = client.post("/api/admin/problems", headers=writer_headers, json=choice_payload()).json()
        assert client.post(f"/api/admin/problems/{created['id']}/submit", headers=match(writer_headers, 1)).status_code == 200
        # 第二位录入员既不能读取也不能编辑他人的题。
        client.post("/api/admin/logout", headers={"X-CSRF-Token": client.cookies.get("admin_csrf_token")})
        other_headers = login(client, "writer2")
        assert client.get(f"/api/admin/problems/{created['id']}", headers=other_headers).status_code == 403
        assert client.post(f"/api/admin/problems/{created['id']}/approve", headers=match(other_headers, 2)).status_code == 403
        client.post("/api/admin/logout", headers={"X-CSRF-Token": client.cookies.get("admin_csrf_token")})
        reviewer_headers = login(client, "reviewer")
        approved = client.post(f"/api/admin/problems/{created['id']}/approve", headers=match(reviewer_headers, 2))
        assert approved.status_code == 200, approved.text

        client.post("/api/admin/logout", headers={"X-CSRF-Token": client.cookies.get("admin_csrf_token")})
        root_headers = login(client)
        original = client.get(f"/api/admin/problems/{created['id']}", headers=root_headers).json()
        published_no = original["problem_id_no"]
        assert published_no and original["open_revision"] is None

        # 已发布题不能直接改：只能开一份草稿副本，线上内容此间保持不变。
        revised = client.post(f"/api/admin/problems/{created['id']}/revise", headers=match(root_headers, original["revision"])).json()
        assert revised["status"] == "draft" and revised["version_no"] == 2 and revised["problem_id_no"] is None
        still_live = client.get(f"/api/admin/problems/{created['id']}", headers=root_headers).json()
        assert still_live["status"] == "approved" and still_live["problem_id_no"] == published_no
        assert still_live["open_revision"]["id"] == revised["id"]
        # 有修订在审期间，线上那一版既不能再开修订也不能删除。
        assert "revise" not in still_live["allowed_actions"] and "delete" not in still_live["allowed_actions"]
        blocked = client.delete(f"/api/admin/problems/{created['id']}", headers=match(root_headers, still_live["revision"]))
        assert blocked.status_code == 409 and "修订稿" in blocked.json()["detail"]

        assert client.post(f"/api/admin/problems/{revised['id']}/submit", headers=match(root_headers, revised["revision"])).status_code == 200
        approved = client.post(f"/api/admin/problems/{revised['id']}/approve", headers=match(root_headers, revised["revision"] + 1))
        assert approved.status_code == 200, approved.text
        # 修订继承线上编号并顶替旧行——组卷靠 problem_id_no 引用，改版后不能失效。
        assert approved.json()["problem_id_no"] == published_no
        assert client.get(f"/api/admin/problems/{created['id']}", headers=root_headers).status_code == 404
        trail = client.get(f"/api/admin/problems/{revised['id']}/audit", headers=root_headers).json()["items"]
        approve_event = next(item for item in trail if item["event"] == "admin_problem_approve")
        assert approve_event["summary"]["replaced_problem_id"] == created["id"]
        assert approve_event["summary"].get("self_review") is True


def test_super_admin_reviewing_others_is_not_marked_self_review(tmp_path):
    """自审豁免只放宽 super_admin 审自己的题；审他人的题走正常复核，不打自审标记。

    注：reviewer 角色当前无法创建题目（create_problem 要求 _is_editor），
    因此"reviewer 自审"在现有代码里不可达，此处不为其写用例。
    """
    with admin_client(tmp_path) as client:
        writer_headers = login(client, "writer")
        created = client.post("/api/admin/problems", headers=writer_headers, json=choice_payload()).json()
        assert client.post(f"/api/admin/problems/{created['id']}/submit", headers=match(writer_headers, 1)).status_code == 200
        client.post("/api/admin/logout", headers={"X-CSRF-Token": client.cookies.get("admin_csrf_token")})
        root_headers = login(client)
        assert client.post(f"/api/admin/problems/{created['id']}/approve", headers=match(root_headers, 2)).status_code == 200
        trail = client.get(f"/api/admin/problems/{created['id']}/audit", headers=root_headers).json()["items"]
        approve_event = next(item for item in trail if item["event"] == "admin_problem_approve")
        assert "self_review" not in approve_event["summary"]


def test_programming_submission_enforced_by_backend(tmp_path):
    with admin_client(tmp_path) as client:
        headers = login(client)
        payload = programming_payload("python", "全测试点通过")
        payload["programming"]["manual_test_cases"] = []
        created = client.post("/api/admin/problems", headers=headers, json=payload).json()
        assert client.post(f"/api/admin/problems/{created['id']}/submit", headers=match(headers, 1)).status_code == 422
        payload = programming_payload("cpp", "全测试点通过")
        created = client.post("/api/admin/problems", headers=headers, json=payload).json()
        assert client.post(f"/api/admin/problems/{created['id']}/submit", headers=match(headers, 1)).status_code == 422


def test_pickable_is_cross_owner_approved_only_and_answer_free(tmp_path):
    """组卷选题面板：approved 题是共享资产，跨负责人可见，且不带答案/解析。

    editor 在题库管理列表里看不见别人的题（_visible_statement 只放 owner/created_by），
    若直接复用该列表组卷，非超管打开选题面板就是一片空白。
    """
    with admin_client(tmp_path) as client:
        root_headers = login(client)
        created = client.post("/api/admin/problems", headers=root_headers, json=choice_payload()).json()
        assert client.post(f"/api/admin/problems/{created['id']}/submit", headers=match(root_headers, 1)).status_code == 200
        assert client.post(f"/api/admin/problems/{created['id']}/approve", headers=match(root_headers, 2)).status_code == 200
        # 另一道留在草稿：不应出现在选题面板。
        client.post("/api/admin/problems", headers=root_headers, json=programming_payload("python"))

        client.post("/api/admin/logout", headers={"X-CSRF-Token": client.cookies.get("admin_csrf_token")})
        writer_headers = login(client, "writer")
        # editor 在管理列表里看不见这道题……
        assert client.get("/api/admin/problems?status=approved", headers=writer_headers).json()["total"] == 0
        assert client.get(f"/api/admin/problems/{created['id']}", headers=writer_headers).status_code == 403
        # ……但选题面板能看见，且字段里没有答案。
        picked = client.get("/api/admin/problems/pickable", headers=writer_headers)
        assert picked.status_code == 200, picked.text
        body = picked.json()
        assert body["total"] == 1
        item = body["items"][0]
        assert item["problem_id_no"] and item["type"] == "choice"
        assert "TCP" in item["stem_text"]
        for forbidden in ("options", "blanks", "analysis", "programming", "ref_code"):
            assert forbidden not in item, forbidden
        # 筛选：题型 + 编程语言。
        assert client.get("/api/admin/problems/pickable?type=programming", headers=writer_headers).json()["total"] == 0
        assert client.get("/api/admin/problems/pickable?sub_type=python", headers=writer_headers).json()["total"] == 0
def zip_testdata_with_case_limits() -> bytes:
    with BytesIO() as stream:
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("1.in", "1 2\n")
            archive.writestr("1.out", "3\n")
            archive.writestr("2.in", "4 5\n")
            archive.writestr("2.out", "9\n")
            archive.writestr("config.yaml", (
                "time_limit: 2s\nmemory_limit: 256mb\n"
                "cases:\n"
                "  1: {score: 50}\n"
                "  2: {score: 50, time_limit_ms: 3000, memory_limit_mb: 64}\n"
            ))
        return stream.getvalue()


def test_zip_per_case_limits_land_on_testcases(tmp_path):
    """config.yaml 的逐点 time_limit_ms / memory_limit_mb 导入后写进 TestCase 和清单。"""
    with admin_client(tmp_path) as client:
        headers = login(client)
        created = client.post("/api/admin/problems", headers=headers, json=programming_payload()).json()
        uploaded = client.post(f"/api/admin/problems/{created['id']}/testdata-zip",
                               headers=match(headers, 1),
                               files={"archive": ("ab.zip", zip_testdata_with_case_limits(), "application/zip")})
        assert uploaded.status_code == 200, uploaded.text
        manifest = uploaded.json()["manifest"]
        assert manifest[0]["time_limit_ms"] is None and manifest[0]["memory_limit_mb"] is None
        assert manifest[1]["time_limit_ms"] == 3000 and manifest[1]["memory_limit_mb"] == 64
        db = client.app.state.session_factory()
        try:
            cases = db.scalars(select(CaseRow).where(CaseRow.problem_id == created["id"])
                               .order_by(CaseRow.sort_order)).all()
            hidden = [c for c in cases if not c.is_sample]
            assert hidden[0].time_limit_ms is None and hidden[0].memory_limit_mb is None
            assert hidden[1].time_limit_ms == 3000 and hidden[1].memory_limit_mb == 64
        finally:
            db.close()


def test_zip_out_of_range_per_case_limit_returns_400(tmp_path):
    """逐点限制超范围要抛错并指明是哪个测试点，不能静默截断。"""
    with BytesIO() as stream:
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("1.in", "1 2\n")
            archive.writestr("1.out", "3\n")
            archive.writestr("config.yaml", "cases:\n  1: {score: 100, memory_limit_mb: 1024}\n")
        raw = stream.getvalue()
    with admin_client(tmp_path) as client:
        headers = login(client)
        created = client.post("/api/admin/problems", headers=headers, json=programming_payload()).json()
        response = client.post(f"/api/admin/problems/{created['id']}/testdata-zip",
                               headers=match(headers, 1),
                               files={"archive": ("bad.zip", raw, "application/zip")})
        assert response.status_code == 400, response.text
        assert "1" in response.json()["detail"]  # 指明是第 1 个测试点


def test_limits_out_of_range_are_rejected(tmp_path):
    """题目级与逐点限制超范围都被 422 拒掉。"""
    with admin_client(tmp_path) as client:
        headers = login(client)
        payload = programming_payload("python")
        payload["programming"]["memory_limit_mb"] = 1024
        response = client.post("/api/admin/problems", headers=headers, json=payload)
        assert response.status_code == 422, response.text
        payload = programming_payload("python")
        payload["programming"]["manual_test_cases"] = [
            {"input": "1", "output": "2", "memory_limit_mb": 1024},
        ]
        response = client.post("/api/admin/problems", headers=headers, json=payload)
        assert response.status_code == 422, response.text
        payload = programming_payload("python")
        payload["programming"]["time_limit_ms"] = 50  # 低于 100
        response = client.post("/api/admin/problems", headers=headers, json=payload)
        assert response.status_code == 422, response.text


def test_unify_limits_sets_problem_level_and_clears_per_case(tmp_path):
    """「统一设定」= 改题目级 + 把所有逐点值清空回到继承，而不是复制到每个测试点。"""
    with admin_client(tmp_path) as client:
        headers = login(client)
        payload = programming_payload("python")
        payload["programming"]["time_limit_ms"] = 2000
        payload["programming"]["memory_limit_mb"] = 256
        payload["programming"]["manual_test_cases"] = [
            {"input": "1", "output": "2", "time_limit_ms": 3000, "memory_limit_mb": 64},
            {"input": "3", "output": "4", "time_limit_ms": 4000, "memory_limit_mb": 128},
        ]
        created = client.post("/api/admin/problems", headers=headers, json=payload).json()

        db = client.app.state.session_factory()
        try:
            hidden = db.scalars(select(CaseRow).where(CaseRow.problem_id == created["id"],
                                                       CaseRow.is_sample.is_(False))).all()
            assert [c.time_limit_ms for c in hidden] == [3000, 4000]
        finally:
            db.close()

        unified = client.post(f"/api/admin/problems/{created['id']}/unify-testcase-limits",
                              headers=match(headers, 1),
                              json={"time_limit_ms": 5000, "memory_limit_mb": 512})
        assert unified.status_code == 200, unified.text
        assert unified.json()["programming"]["time_limit_ms"] == 5000
        assert unified.json()["programming"]["memory_limit_mb"] == 512

        db = client.app.state.session_factory()
        try:
            hidden = db.scalars(select(CaseRow).where(CaseRow.problem_id == created["id"],
                                                       CaseRow.is_sample.is_(False))).all()
            assert all(c.time_limit_ms is None and c.memory_limit_mb is None for c in hidden)
        finally:
            db.close()


def test_zip_out_of_range_problem_level_limit_returns_400(tmp_path):
    """题目级限制走同一套范围校验：config.yaml 不能绕开 512MB 这条硬约束。"""
    with BytesIO() as stream:
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("1.in", "1 2\n")
            archive.writestr("1.out", "3\n")
            archive.writestr("config.yaml", "memory_limit: 4096\ncases:\n  1: {score: 100}\n")
        raw = stream.getvalue()
    with admin_client(tmp_path) as client:
        headers = login(client)
        created = client.post("/api/admin/problems", headers=headers, json=programming_payload()).json()
        response = client.post(f"/api/admin/problems/{created['id']}/testdata-zip",
                               headers=match(headers, 1),
                               files={"archive": ("bad.zip", raw, "application/zip")})
        assert response.status_code == 400, response.text
        assert "memory_limit" in response.json()["detail"]


def test_imported_testcase_meta_can_be_edited(tmp_path):
    """已导入测试点的分值/限时/内存能在界面上直接改，不用重新打包 ZIP。"""
    with admin_client(tmp_path) as client:
        headers = login(client)
        created = client.post("/api/admin/problems", headers=headers, json=programming_payload()).json()
        uploaded = client.post(f"/api/admin/problems/{created['id']}/testdata-zip",
                               headers=match(headers, 1),
                               files={"archive": ("ab.zip", zip_testdata_with_case_limits(), "application/zip")})
        assert uploaded.status_code == 200, uploaded.text
        revision = uploaded.json()["revision"]

        saved = client.put(f"/api/admin/problems/{created['id']}/testdata-cases",
                           headers=match(headers, revision),
                           json={"cases": [
                               {"case_no": 1, "score": 30, "time_limit_ms": 2500, "memory_limit_mb": 128},
                               {"case_no": 2, "score": 70},  # 不给限制 = 回到继承
                           ]})
        assert saved.status_code == 200, saved.text
        manifest = {entry["case_no"]: entry for entry in saved.json()["manifest"]}
        assert manifest[1]["score"] == 30 and manifest[1]["time_limit_ms"] == 2500
        assert manifest[2]["score"] == 70 and manifest[2]["time_limit_ms"] is None

        db = client.app.state.session_factory()
        try:
            cases = {c.case_no: c for c in db.scalars(
                select(CaseRow).where(CaseRow.problem_id == created["id"], CaseRow.input_file.is_not(None)))}
            assert cases[1].score == 30 and cases[1].time_limit_ms == 2500 and cases[1].memory_limit_mb == 128
            assert cases[2].score == 70 and cases[2].time_limit_ms is None and cases[2].memory_limit_mb is None
        finally:
            db.close()

        # 重新读题：清单是从 manifest_json 回填的，改动必须留在里面
        detail = client.get(f"/api/admin/problems/{created['id']}", headers=headers).json()
        package = detail["programming"]["testdata_package"]
        assert {entry["case_no"]: entry["score"] for entry in package["manifest"]} == {1: 30, 2: 70}


def test_imported_testcase_meta_rejects_bad_input(tmp_path):
    """超范围 422、编号对不上 400——静默跳过会让人以为存上了。"""
    with admin_client(tmp_path) as client:
        headers = login(client)
        created = client.post("/api/admin/problems", headers=headers, json=programming_payload()).json()
        uploaded = client.post(f"/api/admin/problems/{created['id']}/testdata-zip",
                               headers=match(headers, 1),
                               files={"archive": ("ab.zip", zip_testdata_with_case_limits(), "application/zip")})
        revision = uploaded.json()["revision"]

        too_big = client.put(f"/api/admin/problems/{created['id']}/testdata-cases",
                             headers=match(headers, revision),
                             json={"cases": [{"case_no": 1, "memory_limit_mb": 1024}]})
        assert too_big.status_code == 422, too_big.text

        unknown = client.put(f"/api/admin/problems/{created['id']}/testdata-cases",
                             headers=match(headers, revision),
                             json={"cases": [{"case_no": 99, "score": 10}]})
        assert unknown.status_code == 400, unknown.text
        assert "99" in unknown.json()["detail"]


def _upload_testdata(client, headers, revision: int = 1):
    """建一道 C++ 题并导入两点测试数据，返回 (problem_id, 上传响应)。"""
    created = client.post("/api/admin/problems", headers=headers, json=programming_payload()).json()
    uploaded = client.post(f"/api/admin/problems/{created['id']}/testdata-zip",
                           headers=match(headers, revision),
                           files={"archive": ("ab.zip", zip_testdata_with_case_limits(), "application/zip")})
    assert uploaded.status_code == 200, uploaded.text
    return created["id"], uploaded.json()


def test_download_single_testcase_file(tmp_path):
    """逐点下载：拿回来的就是当初上传的那份内容，且是附件而不是内联展示。"""
    with admin_client(tmp_path) as client:
        headers = login(client)
        problem_id, _ = _upload_testdata(client, headers)

        got = client.get(f"/api/admin/problems/{problem_id}/testdata/cases/2", params={"side": "in"})
        assert got.status_code == 200, got.text
        assert got.text == "4 5\n"
        assert "attachment" in got.headers["content-disposition"]
        assert "-2.in" in got.headers["content-disposition"]

        out = client.get(f"/api/admin/problems/{problem_id}/testdata/cases/2", params={"side": "out"})
        assert out.text == "9\n"

        # 不存在的测试点 404，不是 500 也不是空文件
        assert client.get(f"/api/admin/problems/{problem_id}/testdata/cases/99").status_code == 404
        # side 只认 in/out，别的值在参数校验就挡掉
        assert client.get(f"/api/admin/problems/{problem_id}/testdata/cases/1",
                          params={"side": "../../etc/passwd"}).status_code == 422


def test_download_testdata_archive_round_trips(tmp_path):
    """整包下载的意义在于**下载→改→再上传**闭合：config.yaml 必须按库里现在的值生成，
    而不是把当初上传的那份原样吐回来，否则界面上改过的分值一下载就丢。"""
    with admin_client(tmp_path) as client:
        headers = login(client)
        problem_id, uploaded = _upload_testdata(client, headers)

        # 先在界面上改一遍逐点元数据
        saved = client.put(f"/api/admin/problems/{problem_id}/testdata-cases",
                           headers=match(headers, uploaded["revision"]),
                           json={"cases": [
                               {"case_no": 1, "score": 30, "time_limit_ms": 2500},
                               {"case_no": 2, "score": 70, "memory_limit_mb": 64},
                           ]})
        assert saved.status_code == 200, saved.text

        got = client.get(f"/api/admin/problems/{problem_id}/testdata/archive")
        assert got.status_code == 200, got.text
        assert got.headers["content-type"] == "application/zip"
        assert "attachment" in got.headers["content-disposition"]

        # 用解析器读回来：生成器与解析器同形是这个特性的立身之本
        parsed = parse_testdata_zip(got.content, max_files=200, max_unpacked_bytes=10_000_000)
        assert [(case.case_no, case.score) for case in parsed.cases] == [(1, 30), (2, 70)]
        assert parsed.cases[0].time_limit_ms == 2500 and parsed.cases[0].memory_limit_mb is None
        assert parsed.cases[1].memory_limit_mb == 64 and parsed.cases[1].time_limit_ms is None
        with zipfile.ZipFile(BytesIO(got.content)) as archive:
            assert sorted(archive.namelist()) == ["1.in", "1.out", "2.in", "2.out", "config.yaml"]
            assert archive.read("1.in") == b"1 2\n"


def test_download_testdata_requires_data_and_permission(tmp_path):
    """没导过数据 404；没权限读这道题 403；没登录 401。"""
    with admin_client(tmp_path) as client:
        headers = login(client)
        bare = client.post("/api/admin/problems", headers=headers, json=programming_payload()).json()
        assert client.get(f"/api/admin/problems/{bare['id']}/testdata/archive").status_code == 404

        problem_id, _ = _upload_testdata(client, headers)
        client.post("/api/admin/logout", headers=headers)
        assert client.get(f"/api/admin/problems/{problem_id}/testdata/archive").status_code == 401

        # 另一个编辑：这道题不是他的，读不到就更不该下载
        other = login(client, "writer2")
        assert client.get(f"/api/admin/problems/{problem_id}/testdata/archive").status_code == 403
        assert client.get(f"/api/admin/problems/{problem_id}/testdata/cases/1",
                          headers=other).status_code == 403


def test_download_testdata_is_audited(tmp_path):
    """判分资产的每一次外流都要留痕，与整卷预览答案同一口径。"""
    with admin_client(tmp_path) as client:
        headers = login(client)
        problem_id, _ = _upload_testdata(client, headers)
        client.get(f"/api/admin/problems/{problem_id}/testdata/archive")
        client.get(f"/api/admin/problems/{problem_id}/testdata/cases/1", params={"side": "out"})

        events = client.get(f"/api/admin/problems/{problem_id}/audit", headers=headers).json()["items"]
        # audit() 会给事件名加 admin_ 前缀，与整卷预览的 admin_paper_preview_answers 同构
        downloads = [item for item in events if item["event"] == "admin_problem_testdata_download"]
        assert len(downloads) == 2
        assert any(item["summary"].get("archive") for item in downloads)
        assert any(item["summary"].get("case_no") == 1 for item in downloads)


def test_unify_limits_also_refreshes_imported_manifest(tmp_path):
    """「统一设定」清空逐点值之后，已导入测试点的清单不能还挂着旧值。"""
    with admin_client(tmp_path) as client:
        headers = login(client)
        created = client.post("/api/admin/problems", headers=headers, json=programming_payload()).json()
        uploaded = client.post(f"/api/admin/problems/{created['id']}/testdata-zip",
                               headers=match(headers, 1),
                               files={"archive": ("ab.zip", zip_testdata_with_case_limits(), "application/zip")})
        assert uploaded.json()["manifest"][1]["time_limit_ms"] == 3000
        unified = client.post(f"/api/admin/problems/{created['id']}/unify-testcase-limits",
                              headers=match(headers, uploaded.json()["revision"]),
                              json={"time_limit_ms": 1500, "memory_limit_mb": 256})
        assert unified.status_code == 200, unified.text
        manifest = unified.json()["programming"]["testdata_package"]["manifest"]
        assert all(entry["time_limit_ms"] is None and entry["memory_limit_mb"] is None for entry in manifest)
        # 分值不属于「限制」，统一设定不该动它
        assert [entry["score"] for entry in manifest] == [50, 50]


def test_problem_delete_blocked_by_lesson_problem_block(tmp_path):
    """题目删除保护（实现计划 v2 §4.5）：被课中练习单题块引用 → 409；解绑后可删。

    与试卷删除保护（admin_papers._paper_delete_blocker）同范式：引用存在即不允许删，
    删除侧不依赖发布检查兜底。
    """
    with admin_client(tmp_path) as client:
        headers = login(client)
        created = client.post("/api/admin/problems", headers=headers, json=choice_payload()).json()
        assert client.post(f"/api/admin/problems/{created['id']}/submit",
                           headers=match(headers, 1)).status_code == 200
        assert client.post(f"/api/admin/problems/{created['id']}/approve",
                           headers=match(headers, 2)).status_code == 200
        approved = client.get(f"/api/admin/problems/{created['id']}", headers=headers).json()
        no = approved["problem_id_no"]

        # 建课包 → 课时 → 课中练习单题块引用这道题
        cat = create_category(client, headers).json()
        course = create_course(client, headers, cat["id"]).json()
        section = add_section(client, headers, course["id"]).json()
        lesson = client.post(f"/api/admin/sections/{section['id']}/lessons", headers=headers,
                             json={"title": "课时 1", "duration_minutes": 30}).json()
        b = client.post(f"/api/admin/lessons/{lesson['id']}/blocks", headers=headers,
                        json={"block_type": "practice", "title": "课中练习",
                              "detail": {"problem": {"problem_id_no": no, "display_no": "1", "score": 10}}}).json()
        assert b["problem"]["problem_id_no"] == no

        # 被引用 → 409，提示先解绑
        blocked = client.delete(f"/api/admin/problems/{created['id']}",
                                headers=match(headers, approved["revision"]))
        assert blocked.status_code == 409
        assert "课中练习块引用" in blocked.json()["detail"]

        # 解绑（删块）后可正常删除
        assert client.delete(f"/api/admin/lesson-blocks/{b['id']}", headers=headers).status_code == 200
        resp = client.delete(f"/api/admin/problems/{created['id']}",
                             headers=match(headers, approved["revision"]))
        assert resp.status_code == 200
