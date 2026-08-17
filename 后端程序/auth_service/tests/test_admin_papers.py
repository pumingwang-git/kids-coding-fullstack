from pathlib import Path

from fastapi.testclient import TestClient

from app.config import DEV_FERNET_KEY, Settings
from app.database import build_database
from app.main import create_app
from app.models import AdminUser, Base, Problem
from app.security import password_hash


PASSWORD = "Admin-pass-123!"


def admin_client(tmp_path: Path) -> TestClient:
    settings = Settings(
        environment="test", database_url=f"sqlite:///{tmp_path / 'papers_test.db'}",
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
        for username, role in (("root", "super_admin"), ("writer", "editor"), ("writer2", "editor")):
            db.add(AdminUser(username=username, password_hash=password_hash.hash(PASSWORD), display_name=username, role=role))
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
    return {"type": "choice", "sub_type": None, "common": {"difficulty": "入门", "source": "自命题", "structure": "单项知识点", "knowledge": [], "stage": [], "business": []}, "stem": "TCP 是面向连接的协议？", "analysis": "", "options": [{"content": "对", "is_correct": True}, {"content": "错", "is_correct": False}], "blanks": [], "programming": None}


def programming_payload(language: str = "cpp") -> dict:
    return {"type": "programming", "sub_type": language, "common": {"difficulty": "普及-", "source": "洛谷", "structure": "综合应用", "knowledge": [], "stage": [], "business": []}, "stem": "输入两个整数，输出和。", "analysis": "", "options": [], "blanks": [], "programming": {"title": "A+B Problem", "pass_condition": "编译通过", "input_format": "两个整数", "output_format": "一个整数", "hints": "无", "samples": [], "ref_code": {"cpp": "int main(){}", "python": "print(1)"}, "manual_test_cases": []}}


def approve_problem(client: TestClient, headers: dict[str, str], payload: dict | None = None) -> dict:
    """建题并直接审核通过（super_admin 自审），返回含 problem_id_no 的详情。"""
    created = client.post("/api/admin/problems", headers=headers, json=payload or choice_payload())
    assert created.status_code == 201, created.text
    problem = created.json()
    assert client.post(f"/api/admin/problems/{problem['id']}/submit", headers=match(headers, 1)).status_code == 200
    approved = client.post(f"/api/admin/problems/{problem['id']}/approve", headers=match(headers, 2))
    assert approved.status_code == 200, approved.text
    detail = client.get(f"/api/admin/problems/{problem['id']}", headers=headers).json()
    assert detail["problem_id_no"]
    return detail


def paper_payload(**overrides) -> dict:
    """试卷 = 内容层。时间/次数/呈现属于链接层，见 link_payload()。"""
    payload = {"title": "C++ 入门测试卷", "description": "", "paper_type": "测试卷", "subject": "cpp",
               "ruleset": "IOI", "score_mode": "testcase", "partial_credit_multi": False,
               "pass_score": None, "questions": []}
    payload.update(overrides)
    return payload


def link_payload(**overrides) -> dict:
    """考试链接 = 场次层。一张卷可有多条。"""
    payload = {"name": "默认场次", "open_at": None, "close_at": None, "duration_minutes": 60,
               "late_start_policy": "truncate", "attempt_limit": 1, "score_policy": "best",
               "penalty_minutes": 0, "feedback_mode": "realtime", "show_analysis": "after_submit",
               "show_score": "immediate", "shuffle_questions": False, "shuffle_options": False}
    payload.update(overrides)
    return payload


def test_paper_crud_total_score_and_revision_guard(tmp_path):
    with admin_client(tmp_path) as client:
        headers = login(client)
        problem = approve_problem(client, headers)
        questions = [{"problem_id_no": problem["problem_id_no"], "score": 20, "sort_order": 0}]
        created = client.post("/api/admin/papers", headers=headers, json=paper_payload(questions=questions))
        assert created.status_code == 201, created.text
        paper = created.json()
        assert paper["status"] == "draft" and paper["revision"] == 1
        assert paper["total_score"] == 20  # 服务端汇总，不信前端传值
        assert paper["questions"][0]["problem"]["type"] == "choice"

        # If-Match 乐观锁：缺头 428，不匹配 409。
        assert client.put(f"/api/admin/papers/{paper['id']}", headers=headers, json=paper_payload()).status_code == 428
        assert client.put(f"/api/admin/papers/{paper['id']}", headers=match(headers, 99), json=paper_payload()).status_code == 409

        updated = client.put(
            f"/api/admin/papers/{paper['id']}", headers=match(headers, 1),
            json=paper_payload(title="改名卷", questions=[{"problem_id_no": problem["problem_id_no"], "score": 35, "sort_order": 0}]),
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["title"] == "改名卷" and updated.json()["total_score"] == 35 and updated.json()["revision"] == 2

        listing = client.get("/api/admin/papers?keyword=改名", headers=headers).json()
        assert listing["total"] == 1 and listing["items"][0]["question_count"] == 1
        assert listing["items"][0]["question_types"] == {"choice": 1}
        counts = client.get("/api/admin/paper-status-counts", headers=headers).json()["counts"]
        assert counts == {"draft": 1, "published": 0, "archived": 0}


def test_publish_validation_checklist(tmp_path):
    with admin_client(tmp_path) as client:
        headers = login(client)
        # 空卷不能发布。
        empty = client.post("/api/admin/papers", headers=headers, json=paper_payload()).json()
        rejected = client.post(f"/api/admin/papers/{empty['id']}/publish", headers=match(headers, 1))
        assert rejected.status_code == 422 and "至少需要一道题" in rejected.json()["detail"]

        # 含未过审/不存在的题不能发布。
        ghost = client.post("/api/admin/papers", headers=headers, json=paper_payload(questions=[{"problem_id_no": "Q999999", "score": 10, "sort_order": 0}])).json()
        rejected = client.post(f"/api/admin/papers/{ghost['id']}/publish", headers=match(headers, 1))
        assert rejected.status_code == 422 and "Q999999" in rejected.json()["detail"]

        # C++ 卷不能含 Python 编程题。
        python_problem = approve_problem(client, headers, programming_payload("python"))
        mixed = client.post("/api/admin/papers", headers=headers, json=paper_payload(questions=[{"problem_id_no": python_problem["problem_id_no"], "score": 10, "sort_order": 0}])).json()
        rejected = client.post(f"/api/admin/papers/{mixed['id']}/publish", headers=match(headers, 1))
        assert rejected.status_code == 422 and "语言与试卷学科不一致" in rejected.json()["detail"]

        # Schema 层拦截（卷层）：pass_score > total、重复题。
        problem = approve_problem(client, headers)
        questions = [{"problem_id_no": problem["problem_id_no"], "score": 10, "sort_order": 0}]
        assert client.post("/api/admin/papers", headers=headers, json=paper_payload(questions=questions, pass_score=11)).status_code == 422
        assert client.post("/api/admin/papers", headers=headers, json=paper_payload(questions=questions * 2)).status_code == 422
        # 时间自洽校验已随字段迁往链接层，见 test_link_schedule_validation。


def test_publish_assigns_number_and_archive_locks(tmp_path):
    with admin_client(tmp_path) as client:
        headers = login(client)
        problem = approve_problem(client, headers)
        created = client.post("/api/admin/papers", headers=headers, json=paper_payload(questions=[{"problem_id_no": problem["problem_id_no"], "score": 100, "sort_order": 0}])).json()
        assert created["paper_id_no"] is None and created["links"] == []  # 发布前没有编号，也没有任何链接

        published = client.post(f"/api/admin/papers/{created['id']}/publish", headers=match(headers, 1))
        assert published.status_code == 200, published.text
        paper = published.json()
        assert paper["paper_id_no"] == f"P{created['id']:06d}"
        assert paper["status"] == "published" and paper["published_at"]
        # 发布不再自动发链接：链接是独立实体，由管理员按场次建。
        assert paper["links"] == [] and paper["link_count"] == 0

        link = client.post(f"/api/admin/papers/{created['id']}/links", headers=headers, json=link_payload(name="三班期中考"))
        assert link.status_code == 201, link.text
        assert link.json()["exam_url"].startswith("/exam/") and link.json()["status"] == "active"

        # 归档即锁定：卷不能编辑，且其下链接一并停用；但归档卷可以删除
        # （锁的是内容不是记录，删除权与编辑权是两个维度）。
        archived = client.post(f"/api/admin/papers/{created['id']}/archive", headers=match(headers, paper["revision"]))
        assert archived.status_code == 200, archived.text
        assert archived.json()["status"] == "archived" and archived.json()["archived_at"]
        assert [item["status"] for item in archived.json()["links"]] == ["disabled"]
        stale = archived.json()["revision"]
        assert client.put(f"/api/admin/papers/{created['id']}", headers=match(headers, stale), json=paper_payload()).status_code == 403
        deleted = client.delete(f"/api/admin/papers/{created['id']}", headers=match(headers, stale))
        assert deleted.status_code == 200, deleted.text

        # 审计流水可查（reviewer/超管）：删卷不删审计。
        trail = client.get(f"/api/admin/papers/{created['id']}/audit", headers=headers).json()["items"]
        events = {item["event"] for item in trail}
        assert {"admin_paper_create", "admin_paper_publish", "admin_paper_link_create", "admin_paper_archive", "admin_paper_delete"} <= events
        delete_event = next(item for item in trail if item["event"] == "admin_paper_delete")
        assert delete_event["summary"]["link_count"] == 1  # 名下的链接随 CASCADE 一并销毁，数量进审计


def test_deleting_referenced_problem_is_blocked_with_paper_title(tmp_path):
    """验收 2（最关键回归点）：组进卷的题不能被删除，且提示试卷名。"""
    with admin_client(tmp_path) as client:
        headers = login(client)
        problem = approve_problem(client, headers)
        created = client.post("/api/admin/papers", headers=headers, json=paper_payload(title="引用保护卷", questions=[{"problem_id_no": problem["problem_id_no"], "score": 50, "sort_order": 0}])).json()

        blocked = client.delete(f"/api/admin/problems/{problem['id']}", headers=match(headers, problem["revision"]))
        assert blocked.status_code == 409, blocked.text
        assert "引用保护卷" in blocked.json()["detail"]

        # 把题从卷里移除后删除放行。
        updated = client.put(f"/api/admin/papers/{created['id']}", headers=match(headers, 1), json=paper_payload(questions=[]))
        assert updated.status_code == 200, updated.text
        removed = client.delete(f"/api/admin/problems/{problem['id']}", headers=match(headers, problem["revision"]))
        assert removed.status_code == 200, removed.text


def test_revise_does_not_break_paper_reference(tmp_path):
    """验收 3：题目改版继承编号，试卷引用不断、看到的是新版。"""
    with admin_client(tmp_path) as client:
        headers = login(client)
        problem = approve_problem(client, headers)
        id_no = problem["problem_id_no"]
        created = client.post("/api/admin/papers", headers=headers, json=paper_payload(questions=[{"problem_id_no": id_no, "score": 30, "sort_order": 0}])).json()

        revised = client.post(f"/api/admin/problems/{problem['id']}/revise", headers=match(headers, problem["revision"])).json()
        edit = choice_payload(); edit["stem"] = "UDP 是无连接的协议？"
        assert client.put(f"/api/admin/problems/{revised['id']}", headers=match(headers, 1), json=edit).status_code == 200
        assert client.post(f"/api/admin/problems/{revised['id']}/submit", headers=match(headers, 2)).status_code == 200
        approved = client.post(f"/api/admin/problems/{revised['id']}/approve", headers=match(headers, 3))
        assert approved.status_code == 200, approved.text
        assert approved.json()["problem_id_no"] == id_no  # 编号继承

        detail = client.get(f"/api/admin/papers/{created['id']}", headers=headers).json()
        assert detail["questions"][0]["problem"]["id"] == revised["id"]  # 解析到新版，引用没断
        published = client.post(f"/api/admin/papers/{created['id']}/publish", headers=match(headers, 1))
        assert published.status_code == 200, published.text


def test_editor_isolated_and_owner_transfer(tmp_path):
    with admin_client(tmp_path) as client:
        writer_headers = login(client, "writer")
        created = client.post("/api/admin/papers", headers=writer_headers, json=paper_payload())
        assert created.status_code == 201, created.text
        paper_id = created.json()["id"]

        client.post("/api/admin/logout", headers={"X-CSRF-Token": client.cookies.get("admin_csrf_token")})
        other_headers = login(client, "writer2")
        assert client.get(f"/api/admin/papers/{paper_id}", headers=other_headers).status_code == 403
        assert client.get("/api/admin/papers", headers=other_headers).json()["total"] == 0
        assert client.put(f"/api/admin/papers/{paper_id}", headers=match(other_headers, 1), json=paper_payload()).status_code == 403
        assert client.patch(f"/api/admin/papers/{paper_id}/owner", headers=match(other_headers, 1), json={"owner_id": 2}).status_code == 403

        client.post("/api/admin/logout", headers={"X-CSRF-Token": client.cookies.get("admin_csrf_token")})
        root_headers = login(client)
        owners = client.get("/api/admin/paper-owners", headers=root_headers).json()["items"]
        writer2_id = next(item["id"] for item in owners if item["display_name"] == "writer2")
        transferred = client.patch(f"/api/admin/papers/{paper_id}/owner", headers=match(root_headers, 1), json={"owner_id": writer2_id})
        assert transferred.status_code == 200, transferred.text
        assert transferred.json()["owner"]["display_name"] == "writer2"
        # 转交后新负责人可以编辑（root 登录覆盖了会话，writer2 需重新登录）。
        client.post("/api/admin/logout", headers={"X-CSRF-Token": client.cookies.get("admin_csrf_token")})
        other_headers = login(client, "writer2")
        assert client.put(f"/api/admin/papers/{paper_id}", headers=match(other_headers, 2), json=paper_payload(title="接手卷")).status_code == 200


def _published_paper(client: TestClient, headers: dict[str, str], questions: list[dict]) -> dict:
    created = client.post("/api/admin/papers", headers=headers, json=paper_payload(questions=questions))
    assert created.status_code == 201, created.text
    published = client.post(f"/api/admin/papers/{created.json()['id']}/publish", headers=match(headers, 1))
    assert published.status_code == 200, published.text
    return published.json()


def test_published_paper_update_must_still_pass_publish_validation(tmp_path):
    """已发布的卷每次 PUT 都必须仍然过得了发布校验，否则校验形同虚设。"""
    with admin_client(tmp_path) as client:
        headers = login(client)
        problem = approve_problem(client, headers)
        questions = [{"problem_id_no": problem["problem_id_no"], "score": 100, "sort_order": 0}]
        paper = _published_paper(client, headers, questions)

        # 清空成 0 题：拒绝，卷仍保持原样。
        rejected = client.put(f"/api/admin/papers/{paper['id']}", headers=match(headers, paper["revision"]), json=paper_payload(questions=[]))
        assert rejected.status_code == 422 and "至少需要一道题" in rejected.json()["detail"]
        # 塞不存在的题：拒绝。
        rejected = client.put(f"/api/admin/papers/{paper['id']}", headers=match(headers, paper["revision"]), json=paper_payload(questions=[{"problem_id_no": "Q999999", "score": 10, "sort_order": 0}]))
        assert rejected.status_code == 422 and "Q999999" in rejected.json()["detail"]
        intact = client.get(f"/api/admin/papers/{paper['id']}", headers=headers).json()
        assert intact["status"] == "published" and intact["total_score"] == 100
        # 合法修改（改名/调及格分）照常放行。
        ok = client.put(f"/api/admin/papers/{paper['id']}", headers=match(headers, paper["revision"]), json=paper_payload(questions=questions, title="改名仍合法", pass_score=60))
        assert ok.status_code == 200, ok.text
        assert ok.json()["title"] == "改名仍合法" and ok.json()["pass_score"] == 60


def test_republish_is_rejected_as_conflict_not_as_permission(tmp_path):
    """重复发布必须报 409 + 说清原因，不能和「没权限」共用一句 403。

    前端组卷弹窗曾对已发布卷仍摆出「保存并发布」：PUT 先成功落库、紧跟的 publish 被这里挡回，
    界面显示「没有执行该试卷操作的权限」而改动其实已经保存——两种拒绝共用一句文案，
    直接把排查方向带到了账号权限上。归档卷仍应按「归档即锁定」报 403。
    """
    with admin_client(tmp_path) as client:
        headers = login(client)
        problem = approve_problem(client, headers)
        questions = [{"problem_id_no": problem["problem_id_no"], "score": 100, "sort_order": 0}]
        paper = _published_paper(client, headers, questions)

        again = client.post(f"/api/admin/papers/{paper['id']}/publish", headers=match(headers, paper["revision"]))
        assert again.status_code == 409, again.text
        assert "已发布" in again.json()["detail"] and "保存修改" in again.json()["detail"]
        # 被拒的发布不留痕迹：状态、编号、revision 一律不动。
        intact = client.get(f"/api/admin/papers/{paper['id']}", headers=headers).json()
        assert intact["status"] == "published" and intact["revision"] == paper["revision"]
        assert intact["paper_id_no"] == paper["paper_id_no"]

        # 归档卷是另一回事：锁定，仍报 403。
        archived = client.post(f"/api/admin/papers/{paper['id']}/archive", headers=match(headers, paper["revision"]))
        assert archived.status_code == 200, archived.text
        locked = client.post(f"/api/admin/papers/{paper['id']}/publish", headers=match(headers, archived.json()["revision"]))
        assert locked.status_code == 403 and "权限" in locked.json()["detail"]


def test_blank_title_is_rejected(tmp_path):
    """空标题/纯空格标题不能建卷：删题时的引用保护靠试卷名指引管理员。"""
    with admin_client(tmp_path) as client:
        headers = login(client)
        assert client.post("/api/admin/papers", headers=headers, json=paper_payload(title="")).status_code == 422
        assert client.post("/api/admin/papers", headers=headers, json=paper_payload(title="   ")).status_code == 422
        # title 整个省略也要拦住：Pydantic 不校验默认值，靠 title 必填（无 default）堵死这条路。
        omitted = paper_payload(); omitted.pop("title")
        assert client.post("/api/admin/papers", headers=headers, json=omitted).status_code == 422


def test_one_paper_many_links_and_isolated_reset(tmp_path):
    """两层模型的核心：一卷多链接，各自独立配置，单条重置不波及其他。"""
    with admin_client(tmp_path) as client:
        headers = login(client)
        problem = approve_problem(client, headers)
        paper = _published_paper(client, headers, [{"problem_id_no": problem["problem_id_no"], "score": 100, "sort_order": 0}])

        exam = client.post(f"/api/admin/papers/{paper['id']}/links", headers=headers,
                           json=link_payload(name="三班期中考", duration_minutes=90, attempt_limit=1, show_analysis="after_close"))
        practice = client.post(f"/api/admin/papers/{paper['id']}/links", headers=headers,
                               json=link_payload(name="课后自测", duration_minutes=None, attempt_limit=0, show_analysis="after_submit"))
        assert exam.status_code == 201 and practice.status_code == 201, (exam.text, practice.text)
        exam, practice = exam.json(), practice.json()

        # 同一张卷、同一份题，两条链接各自独立的考试安排。
        assert exam["attempt_limit"] == 1 and practice["attempt_limit"] == 0
        assert exam["show_analysis"] == "after_close" and practice["show_analysis"] == "after_submit"
        assert exam["exam_url"] != practice["exam_url"]

        listing = client.get(f"/api/admin/papers/{paper['id']}/links", headers=headers).json()
        assert len(listing["items"]) == 2
        assert client.get("/api/admin/papers", headers=headers).json()["items"][0]["link_count"] == 2

        # 只重置期中考这一条，自测链接不受影响——这正是拆两层要换来的能力。
        reset = client.post(f"/api/admin/links/{exam['id']}/reset-token", headers=match(headers, exam["revision"]))
        assert reset.status_code == 200, reset.text
        assert reset.json()["exam_url"] != exam["exam_url"]
        after = client.get(f"/api/admin/papers/{paper['id']}/links", headers=headers).json()["items"]
        assert next(i for i in after if i["name"] == "课后自测")["exam_url"] == practice["exam_url"]

        # 停用一条，另一条仍可用。
        disabled = client.post(f"/api/admin/links/{exam['id']}/disable", headers=match(headers, reset.json()["revision"]))
        assert disabled.status_code == 200 and disabled.json()["status"] == "disabled"
        assert client.get("/api/admin/papers", headers=headers).json()["items"][0]["active_link_count"] == 1


def test_link_name_required_and_unique_per_paper(tmp_path):
    with admin_client(tmp_path) as client:
        headers = login(client)
        problem = approve_problem(client, headers)
        paper = _published_paper(client, headers, [{"problem_id_no": problem["problem_id_no"], "score": 100, "sort_order": 0}])
        assert client.post(f"/api/admin/papers/{paper['id']}/links", headers=headers, json=link_payload(name="")).status_code == 422
        assert client.post(f"/api/admin/papers/{paper['id']}/links", headers=headers, json=link_payload(name="   ")).status_code == 422
        omitted = link_payload(); omitted.pop("name")
        assert client.post(f"/api/admin/papers/{paper['id']}/links", headers=headers, json=omitted).status_code == 422

        assert client.post(f"/api/admin/papers/{paper['id']}/links", headers=headers, json=link_payload(name="三班")).status_code == 201
        dup = client.post(f"/api/admin/papers/{paper['id']}/links", headers=headers, json=link_payload(name="三班"))
        assert dup.status_code == 409 and "名称不能重复" in dup.json()["detail"]


def test_link_schedule_validation(tmp_path):
    """时间自洽校验随字段迁到链接层，取值规则不变。"""
    with admin_client(tmp_path) as client:
        headers = login(client)
        problem = approve_problem(client, headers)
        paper = _published_paper(client, headers, [{"problem_id_no": problem["problem_id_no"], "score": 100, "sort_order": 0}])
        url = f"/api/admin/papers/{paper['id']}/links"
        reversed_window = {"open_at": "2026-08-06T08:00:00Z", "close_at": "2026-08-06T07:00:00Z"}
        assert client.post(url, headers=headers, json=link_payload(**reversed_window)).status_code == 422
        narrow = {"open_at": "2026-08-06T08:00:00Z", "close_at": "2026-08-06T08:30:00Z",
                  "duration_minutes": 60, "late_start_policy": "block"}
        assert client.post(url, headers=headers, json=link_payload(**narrow)).status_code == 422
        # 同样的窗口配 truncate 是合法的：截断到结束时间即可。
        ok = dict(narrow, late_start_policy="truncate")
        assert client.post(url, headers=headers, json=link_payload(**ok)).status_code == 201


def test_links_only_on_published_paper(tmp_path):
    """草稿卷不能建链接：没有可考的内容，链接就没有意义。
    报 409「卷的状态不行」而不是 403「人没权限」——权限与状态分两句话。"""
    with admin_client(tmp_path) as client:
        headers = login(client)
        problem = approve_problem(client, headers)
        draft = client.post("/api/admin/papers", headers=headers,
                            json=paper_payload(questions=[{"problem_id_no": problem["problem_id_no"], "score": 100, "sort_order": 0}])).json()
        denied = client.post(f"/api/admin/papers/{draft['id']}/links", headers=headers, json=link_payload())
        assert denied.status_code == 409 and "尚未发布或已归档" in denied.json()["detail"]


# ==================== 整卷预览 ====================


def multi_choice_payload() -> dict:
    return {"type": "multi_choice", "sub_type": None, "common": {"difficulty": "普及", "source": "CSP-J", "structure": "多项知识点", "knowledge": [], "stage": [], "business": []}, "stem": "哪些是传输层协议？", "analysis": "TCP、UDP 工作在传输层。", "options": [{"content": "TCP", "is_correct": True}, {"content": "UDP", "is_correct": True}, {"content": "IP", "is_correct": False}, {"content": "HTTP", "is_correct": False}], "blanks": [], "programming": None}


def judge_payload() -> dict:
    return {"type": "judge", "sub_type": None, "common": {"difficulty": "入门", "source": "自命题", "structure": "单项知识点", "knowledge": [], "stage": [], "business": []}, "stem": "TCP 是面向连接的协议。", "analysis": "TCP 建立连接后才传数据。", "options": [{"content": "对", "is_correct": True}, {"content": "错", "is_correct": False}], "blanks": [], "programming": None}


def fill_payload() -> dict:
    return {"type": "fill", "sub_type": None, "common": {"difficulty": "入门", "source": "自命题", "structure": "单项知识点", "knowledge": [], "stage": [], "business": []}, "stem": "HTTP 的默认端口是 \\placeholder[port]{}。", "analysis": "RFC 定义。", "options": [], "blanks": [{"blank_index": 0, "blank_key": "port", "answer": "80"}], "programming": None}


def _five_type_paper(client: TestClient, headers: dict[str, str]) -> tuple[dict, dict]:
    """五种题型各一道建卷（root 建题，草稿卷，总分 100 / 及格 60）。"""
    prog = programming_payload("python")
    prog["programming"]["samples"] = [{"input": "1 2", "output": "3"}]
    problems = {
        "choice": approve_problem(client, headers, choice_payload()),
        "multi": approve_problem(client, headers, multi_choice_payload()),
        "judge": approve_problem(client, headers, judge_payload()),
        "fill": approve_problem(client, headers, fill_payload()),
        "prog": approve_problem(client, headers, prog),
    }
    order = ["choice", "multi", "judge", "fill", "prog"]
    questions = [{"problem_id_no": problems[key]["problem_id_no"], "score": 20, "sort_order": index} for index, key in enumerate(order)]
    created = client.post("/api/admin/papers", headers=headers, json=paper_payload(questions=questions, pass_score=60))
    assert created.status_code == 201, created.text
    return created.json(), problems


FORBIDDEN_ANSWER_KEYS = {"is_correct", "answer", "analysis", "blanks", "pass_condition", "ref_code", "difficulty", "source"}


def _assert_no_answer_keys(node, path: str = "$"):
    """递归断言：学生卷任何层级都不出现答案相关键（缺键，不是给空值）。"""
    if isinstance(node, dict):
        leaked = FORBIDDEN_ANSWER_KEYS & set(node)
        assert not leaked, f"{path} 泄漏答案键：{leaked}"
        for key, value in node.items():
            _assert_no_answer_keys(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, item in enumerate(node):
            _assert_no_answer_keys(item, f"{path}[{index}]")


def test_preview_student_view_never_carries_answer_keys(tmp_path):
    """学生卷（with_answers=0）：答案键在整个响应树里递归不存在。"""
    with admin_client(tmp_path) as client:
        headers = login(client)
        paper, _ = _five_type_paper(client, headers)
        preview = client.get(f"/api/admin/papers/{paper['id']}/preview", headers=headers)
        assert preview.status_code == 200, preview.text
        body = preview.json()
        assert body["with_answers"] is False
        _assert_no_answer_keys(body)
        # 题面与结构照常给：学生卷也要能排版。
        assert [q["type"] for q in body["questions"]] == ["choice", "multi_choice", "judge", "fill", "programming"]
        assert body["questions"][0]["options"][0] == {"label": "A", "content": "对"}


def test_preview_answers_reveal_fields_and_write_audit(tmp_path):
    """教师卷（with_answers=1）带答案字段且必写审计；学生卷请求不写。"""
    with admin_client(tmp_path) as client:
        headers = login(client)
        paper, _ = _five_type_paper(client, headers)

        client.get(f"/api/admin/papers/{paper['id']}/preview?with_answers=0", headers=headers)
        events = {item["event"] for item in client.get(f"/api/admin/papers/{paper['id']}/audit", headers=headers).json()["items"]}
        assert "admin_paper_preview_answers" not in events

        revealed = client.get(f"/api/admin/papers/{paper['id']}/preview?with_answers=1", headers=headers)
        assert revealed.status_code == 200, revealed.text
        body = revealed.json()
        assert body["with_answers"] is True
        choice = body["questions"][0]
        assert "analysis" in choice and choice["difficulty"] and choice["source"]
        assert body["questions"][2]["analysis"] == "TCP 建立连接后才传数据。"  # 判断题带了解析
        assert choice["options"][0]["is_correct"] is True
        # alternatives 是空的也照样下发：审卷人要看得见"这个空还接受哪些写法"
        assert body["questions"][3]["blanks"] == [
            {"blank_index": 0, "blank_key": "port", "answer": "80", "alternatives": []}
        ]
        assert body["questions"][4]["programming"]["pass_condition"] == "编译通过"
        assert body["questions"][4]["programming"]["ref_code"] == {"language": "python", "code": "print(1)"}

        events = {item["event"] for item in client.get(f"/api/admin/papers/{paper['id']}/audit", headers=headers).json()["items"]}
        assert "admin_paper_preview_answers" in events


def test_preview_owner_reads_answers_of_others_problems(tmp_path):
    """口子验收：卷负责人 with_answers=1 能读到别人题的答案（卷级授权）。"""
    with admin_client(tmp_path) as client:
        root_headers = login(client)
        problem = approve_problem(client, root_headers)  # 题是 root 的
        client.post("/api/admin/logout", headers={"X-CSRF-Token": client.cookies.get("admin_csrf_token")})

        writer_headers = login(client, "writer")
        created = client.post("/api/admin/papers", headers=writer_headers,
                              json=paper_payload(questions=[{"problem_id_no": problem["problem_id_no"], "score": 10, "sort_order": 0}]))
        assert created.status_code == 201, created.text
        preview = client.get(f"/api/admin/papers/{created.json()['id']}/preview?with_answers=1", headers=writer_headers)
        assert preview.status_code == 200, preview.text
        assert preview.json()["questions"][0]["options"][0]["is_correct"] is True


def test_preview_permission_denied_and_not_found(tmp_path):
    """别人的卷 403（文案与其他试卷操作一致）；不存在的卷 404。"""
    with admin_client(tmp_path) as client:
        writer_headers = login(client, "writer")
        created = client.post("/api/admin/papers", headers=writer_headers, json=paper_payload())
        assert created.status_code == 201, created.text
        client.post("/api/admin/logout", headers={"X-CSRF-Token": client.cookies.get("admin_csrf_token")})

        other_headers = login(client, "writer2")
        denied = client.get(f"/api/admin/papers/{created.json()['id']}/preview", headers=other_headers)
        assert denied.status_code == 403 and "权限" in denied.json()["detail"]
        denied = client.get(f"/api/admin/papers/{created.json()['id']}/preview?with_answers=1", headers=other_headers)
        assert denied.status_code == 403
        missing = client.get("/api/admin/papers/999999/preview", headers=other_headers)
        assert missing.status_code == 404 and "不存在" in missing.json()["detail"]


def test_preview_missing_question_returns_placeholder(tmp_path):
    """题被删/不存在：占位项标 missing，不抛 500，其余题照常渲染。"""
    with admin_client(tmp_path) as client:
        headers = login(client)
        problem = approve_problem(client, headers)
        ghost = client.post("/api/admin/papers", headers=headers, json=paper_payload(questions=[
            {"problem_id_no": "Q999999", "score": 10, "sort_order": 0},
            {"problem_id_no": problem["problem_id_no"], "score": 20, "sort_order": 1},
        ]))
        assert ghost.status_code == 201, ghost.text
        for variant in ("0", "1"):
            preview = client.get(f"/api/admin/papers/{ghost.json()['id']}/preview?with_answers={variant}", headers=headers)
            assert preview.status_code == 200, preview.text
            questions = preview.json()["questions"]
            assert questions[0]["missing"] is True and questions[0]["problem_id_no"] == "Q999999"
            assert "type" not in questions[0] and "stem" not in questions[0]
            assert questions[1]["missing"] is False and questions[1]["type"] == "choice"


def test_preview_marks_unapproved_problem(tmp_path):
    """编号还在、状态已不是 approved 的题：payload 标 approved=false，与 _publish_error 同口径。
    正常流程产生不了这种行（approve 删旧行、delete 删整行），这里直接改库模拟防御场景。
    """
    with admin_client(tmp_path) as client:
        headers = login(client)
        problem = approve_problem(client, headers)
        created = client.post("/api/admin/papers", headers=headers,
                              json=paper_payload(questions=[{"problem_id_no": problem["problem_id_no"], "score": 10, "sort_order": 0}]))
        assert created.status_code == 201, created.text
        preview = client.get(f"/api/admin/papers/{created.json()['id']}/preview", headers=headers).json()
        assert preview["questions"][0]["approved"] is True

        db = client.app.state.session_factory()
        try:
            row = db.get(Problem, problem["id"])
            row.status = "draft"
            db.commit()
        finally:
            db.close()
        for variant in ("0", "1"):
            preview = client.get(f"/api/admin/papers/{created.json()['id']}/preview?with_answers={variant}", headers=headers).json()
            assert preview["questions"][0]["approved"] is False
            assert preview["questions"][0]["missing"] is False  # 不是缺题：题面照渲染，只多一个标记


def test_preview_all_five_types_field_completeness(tmp_path):
    """五题型字段完整性：教师卷逐题核对结构，学生卷核对裁剪后结构。"""
    with admin_client(tmp_path) as client:
        headers = login(client)
        paper, problems = _five_type_paper(client, headers)
        body = client.get(f"/api/admin/papers/{paper['id']}/preview?with_answers=1", headers=headers).json()

        assert body["title"] == "C++ 入门测试卷" and body["status"] == "draft"
        assert body["total_score"] == 100 and body["pass_score"] == 60
        assert body["paper_type"] == "测试卷" and body["subject"] == "cpp" and body["ruleset"] == "IOI"
        assert body["score_mode"] == "testcase" and body["partial_credit_multi"] is False
        assert [q["sort_order"] for q in body["questions"]] == [0, 1, 2, 3, 4]
        assert all(q["score"] == 20 and q["missing"] is False and q["approved"] is True for q in body["questions"])
        assert [q["problem_id_no"] for q in body["questions"]] == [problems[key]["problem_id_no"] for key in ("choice", "multi", "judge", "fill", "prog")]

        choice, multi, judge, fill, prog = body["questions"]
        assert [o["label"] for o in choice["options"]] == ["A", "B"]
        assert [o["is_correct"] for o in multi["options"]] == [True, True, False, False]
        assert [o["content"] for o in judge["options"]] == ["对", "错"]
        assert fill["blanks"][0]["answer"] == "80"
        detail = prog["programming"]
        assert detail["title"] == "A+B Problem"
        assert detail["input_format"] == "两个整数" and detail["output_format"] == "一个整数" and detail["hints"] == "无"
        assert detail["samples"] == [{"input": "1 2", "output": "3"}]
        assert detail["time_limit_ms"] == 1000 and detail["memory_limit_mb"] == 256
        assert detail["ref_code"]["language"] == "python" and detail["ref_code"]["code"]
        assert prog["sub_type"] == "python"

        student = client.get(f"/api/admin/papers/{paper['id']}/preview", headers=headers).json()
        assert [o["label"] for o in student["questions"][0]["options"]] == ["A", "B"]  # 结构保留
        assert "is_correct" not in student["questions"][0]["options"][0]
        assert set(student["questions"][4]["programming"]) >= {"title", "input_format", "output_format", "hints", "samples", "time_limit_ms", "memory_limit_mb"}



# ==================== 链接管理模块（归档卷删除 / 启用 / 全局列表 / 考前提醒）====================


def _archived_paper_with_links(client: TestClient, headers: dict[str, str], link_names: list[str]) -> tuple[dict, list[dict]]:
    """发布一张卷、建好链接、再归档（链接被连带停用），返回归档后的卷与链接清单。"""
    problem = approve_problem(client, headers)
    paper = _published_paper(client, headers, [{"problem_id_no": problem["problem_id_no"], "score": 100, "sort_order": 0}])
    links = []
    for name in link_names:
        created = client.post(f"/api/admin/papers/{paper['id']}/links", headers=headers, json=link_payload(name=name))
        assert created.status_code == 201, created.text
        links.append(created.json())
    archived = client.post(f"/api/admin/papers/{paper['id']}/archive", headers=match(headers, paper["revision"]))
    assert archived.status_code == 200, archived.text
    return archived.json(), links


def test_archived_paper_delete_permission_matrix(tmp_path):
    """归档卷删除权：owner（editor）可删；其他 editor 与 reviewer 403；转让负责人放行归档卷。"""
    with admin_client(tmp_path) as client:
        # 补一个 reviewer 账号（admin_client 只建 root/writer/writer2）。
        db = client.app.state.session_factory()
        try:
            db.add(AdminUser(username="auditor", password_hash=password_hash.hash(PASSWORD), display_name="auditor", role="reviewer"))
            db.commit()
        finally:
            db.close()

        root = login(client)
        paper, _ = _archived_paper_with_links(client, root, ["三班期中考"])
        assert "delete" in paper["allowed_actions"]  # 超管：归档卷给出 delete

        other = login(client, "writer2")
        assert client.get(f"/api/admin/papers/{paper['id']}", headers=other).status_code == 403  # 别人的卷，看都看不到
        assert client.delete(f"/api/admin/papers/{paper['id']}", headers=match(other, paper["revision"])).status_code == 403
        auditor = login(client, "auditor")
        audited = client.get(f"/api/admin/papers/{paper['id']}", headers=auditor).json()
        assert "delete" not in audited["allowed_actions"]  # reviewer 只读
        assert client.delete(f"/api/admin/papers/{paper['id']}", headers=match(auditor, paper["revision"])).status_code == 403

        # 超管把归档卷转给另一个 editor（转让对归档卷放行），对方即获得删除权。
        # 注意 TestClient 共享 cookie 罐：每次切角色都要重新 login，否则请求带着上一个人的会话。
        root = login(client)
        owners = client.get("/api/admin/paper-owners", headers=root).json()["items"]
        writer2_id = next(item["id"] for item in owners if item["display_name"] == "writer2")
        transferred = client.patch(f"/api/admin/papers/{paper['id']}/owner", headers=match(root, paper["revision"]), json={"owner_id": writer2_id})
        assert transferred.status_code == 200, transferred.text
        other = login(client, "writer2")
        new_owner_view = client.get(f"/api/admin/papers/{paper['id']}", headers=other).json()
        assert "delete" in new_owner_view["allowed_actions"]
        deleted = client.delete(f"/api/admin/papers/{paper['id']}", headers=match(other, transferred.json()["revision"]))
        assert deleted.status_code == 200, deleted.text
        assert client.get(f"/api/admin/papers/{paper['id']}", headers=other).status_code == 404


def test_archived_paper_delete_cascades_links_with_audit_count(tmp_path):
    """删归档卷：名下链接 CASCADE 一并销毁，审计 paper_delete 带 link_count。"""
    with admin_client(tmp_path) as client:
        headers = login(client)
        paper, _ = _archived_paper_with_links(client, headers, ["三班期中考", "四班期中考"])
        listing = client.get(f"/api/admin/papers/{paper['id']}/links", headers=headers).json()
        assert len(listing["items"]) == 2

        deleted = client.delete(f"/api/admin/papers/{paper['id']}", headers=match(headers, paper["revision"]))
        assert deleted.status_code == 200, deleted.text
        # 链接表已清空（卷已 404，用全局列表验证）。
        remaining = client.get("/api/admin/exam-links", headers=headers).json()
        assert remaining["total"] == 0
        trail = client.get(f"/api/admin/papers/{paper['id']}/audit", headers=headers).json()["items"]
        event = next(item for item in trail if item["event"] == "admin_paper_delete")
        assert event["summary"]["link_count"] == 2


def test_published_paper_cannot_be_deleted_directly(tmp_path):
    """已发布卷不给一步销毁的路径：先归档（连带停链接）再删。"""
    with admin_client(tmp_path) as client:
        headers = login(client)
        problem = approve_problem(client, headers)
        paper = _published_paper(client, headers, [{"problem_id_no": problem["problem_id_no"], "score": 100, "sort_order": 0}])
        assert "delete" not in paper["allowed_actions"]
        assert client.delete(f"/api/admin/papers/{paper['id']}", headers=match(headers, paper["revision"])).status_code == 403


def test_link_disable_then_enable_and_archived_enable_is_409(tmp_path):
    """启用是停用的反向操作；归档卷的链接启用必须 409 说「卷的状态」，不能 403 说「人没权限」。"""
    with admin_client(tmp_path) as client:
        headers = login(client)
        problem = approve_problem(client, headers)
        paper = _published_paper(client, headers, [{"problem_id_no": problem["problem_id_no"], "score": 100, "sort_order": 0}])
        link = client.post(f"/api/admin/papers/{paper['id']}/links", headers=headers, json=link_payload(name="三班期中考")).json()

        disabled = client.post(f"/api/admin/links/{link['id']}/disable", headers=match(headers, link["revision"]))
        assert disabled.status_code == 200 and disabled.json()["status"] == "disabled"
        again = client.post(f"/api/admin/links/{link['id']}/disable", headers=match(headers, disabled.json()["revision"]))
        assert again.status_code == 409 and "已经是停用状态" in again.json()["detail"]

        enabled = client.post(f"/api/admin/links/{link['id']}/enable", headers=match(headers, disabled.json()["revision"]))
        assert enabled.status_code == 200 and enabled.json()["status"] == "active"
        assert client.post(f"/api/admin/links/{link['id']}/enable", headers=match(headers, enabled.json()["revision"])).status_code == 409

        # 归档（连带停用链接）后：启用报 409 且文案含「已归档」——本期核心回归点。
        current = client.get(f"/api/admin/papers/{paper['id']}", headers=headers).json()
        archived = client.post(f"/api/admin/papers/{paper['id']}/archive", headers=match(headers, current["revision"])).json()
        link_view = next(item for item in archived["links"] if item["id"] == link["id"])
        assert link_view["status"] == "disabled"
        denied = client.post(f"/api/admin/links/{link['id']}/enable", headers=match(headers, link_view["revision"]))
        assert denied.status_code == 409 and "已归档" in denied.json()["detail"], denied.text

        # 归档卷的链接仍可删除（删除权与卷的删除权同源）。
        deleted = client.delete(f"/api/admin/links/{link['id']}", headers=match(headers, link_view["revision"]))
        assert deleted.status_code == 200, deleted.text


def test_exam_links_global_list_filters_and_visibility(tmp_path):
    """跨卷全局列表：可见范围、keyword（链接名/试卷名/编号）、status/phase/paper_id/owner_id、分页。"""
    with admin_client(tmp_path) as client:
        root = login(client)
        problem = approve_problem(client, root)
        questions = [{"problem_id_no": problem["problem_id_no"], "score": 100, "sort_order": 0}]
        mine = _published_paper(client, root, questions)
        future = {"open_at": "2099-01-01T00:00:00Z", "close_at": "2099-01-01T02:00:00Z"}
        running = client.post(f"/api/admin/papers/{mine['id']}/links", headers=root, json=link_payload(name="进行中的场")).json()
        pending = client.post(f"/api/admin/papers/{mine['id']}/links", headers=root, json=link_payload(name="未开始的场", **future)).json()
        client.post(f"/api/admin/links/{running['id']}/disable", headers=match(root, running["revision"]))

        # 另一个 editor 的卷与链接（root 是超管可见全部，换 writer 视角验证可见范围）。
        # writer 直接引用 root 已审核通过的题：发布校验只看 approved，不看题的归属。
        # TestClient 共享 cookie 罐：切角色必须重新 login。
        writer = login(client, "writer")
        wpaper = _published_paper(client, writer, [{"problem_id_no": problem["problem_id_no"], "score": 100, "sort_order": 0}])
        client.post(f"/api/admin/papers/{wpaper['id']}/links", headers=writer, json=link_payload(name="writer 的场"))

        writer_listing = client.get("/api/admin/exam-links", headers=writer).json()
        assert writer_listing["total"] == 1 and writer_listing["items"][0]["name"] == "writer 的场"

        root = login(client)
        all_links = client.get("/api/admin/exam-links", headers=root).json()
        assert all_links["total"] == 3
        row = next(item for item in all_links["items"] if item["id"] == running["id"])
        assert row["paper"]["paper_id_no"] == mine["paper_id_no"] and row["owner"]["display_name"] == "root"
        assert row["phase"] == "running" and row["status"] == "disabled" and "enable" in row["allowed_actions"]
        assert next(item for item in all_links["items"] if item["id"] == pending["id"])["phase"] == "not_started"

        # keyword 同时命中链接名 / 试卷名 / 试卷编号。
        assert client.get("/api/admin/exam-links?keyword=未开始", headers=root).json()["total"] == 1
        assert client.get("/api/admin/exam-links?keyword=入门测试卷", headers=root).json()["total"] == 3  # 两张卷都叫默认标题
        assert client.get("/api/admin/exam-links", headers=root, params={"keyword": mine["paper_id_no"]}).json()["total"] == 2  # 编号只命中一张卷

        # status / phase / paper_id / owner_id 各过滤一遍。
        assert client.get("/api/admin/exam-links?status=disabled", headers=root).json()["total"] == 1
        assert client.get("/api/admin/exam-links?phase=not_started", headers=root).json()["total"] == 1
        assert client.get("/api/admin/exam-links?phase=running", headers=root).json()["total"] == 2  # 无窗口的两条都算 running（含停用那条）
        assert client.get("/api/admin/exam-links", headers=root, params={"paper_id": mine["id"]}).json()["total"] == 2
        owners = client.get("/api/admin/paper-owners", headers=root).json()["items"]
        writer_id = next(item["id"] for item in owners if item["display_name"] == "writer")
        assert client.get("/api/admin/exam-links", headers=root, params={"owner_id": writer_id}).json()["total"] == 1

        # 计数与分页。
        counts = client.get("/api/admin/exam-link-counts", headers=root).json()["counts"]
        assert counts == {"active": 2, "disabled": 1, "all": 3}
        paged = client.get("/api/admin/exam-links?page=2&size=2", headers=root).json()
        assert paged["total"] == 3 and len(paged["items"]) == 1


def test_link_reminder_fields_validation(tmp_path):
    """考前提醒：规范化落库 + 死配置逐条拦截。"""
    with admin_client(tmp_path) as client:
        headers = login(client)
        problem = approve_problem(client, headers)
        paper = _published_paper(client, headers, [{"problem_id_no": problem["problem_id_no"], "score": 100, "sort_order": 0}])
        url = f"/api/admin/papers/{paper['id']}/links"

        # 规范化：去重、降序、容忍中文逗号与空格。
        ok = client.post(url, headers=headers, json=link_payload(name="规范化", duration_minutes=60, remind_minutes="10, 30，10"))
        assert ok.status_code == 201 and ok.json()["remind_minutes"] == "30,10", ok.text
        # 非数字 / 越界 / 超个数。
        assert client.post(url, headers=headers, json=link_payload(name="坏值1", remind_minutes="abc")).status_code == 422
        assert client.post(url, headers=headers, json=link_payload(name="坏值2", remind_minutes="0")).status_code == 422
        assert client.post(url, headers=headers, json=link_payload(name="坏值3", remind_minutes="1441")).status_code == 422
        assert client.post(url, headers=headers, json=link_payload(name="坏值4", remind_minutes="60,50,40,30,20,10")).status_code == 422
        # 提醒点 ≥ 时长：永远不会触发。
        big = client.post(url, headers=headers, json=link_payload(name="死配置1", duration_minutes=30, remind_minutes="30"))
        assert big.status_code == 422 and "必须小于考试时长" in big.text
        # 不限时且无关闭时间：算不出剩余时间。
        no_clock = client.post(url, headers=headers, json=link_payload(name="死配置2", duration_minutes=None, remind_minutes="10"))
        assert no_clock.status_code == 422 and "算不出剩余时间" in no_clock.text
        # 未设开放时间却配提前进入。
        no_open = client.post(url, headers=headers, json=link_payload(name="死配置3", entry_open_minutes=15))
        assert no_open.status_code == 422 and "无需配置提前进入" in no_open.text
        # 要求确认已读但须知为空。
        ack = client.post(url, headers=headers, json=link_payload(name="死配置4", notice_ack_required=True, notice=""))
        assert ack.status_code == 422 and "须知不能为空" in ack.text
        # 合法组合全量落库。
        full = link_payload(name="完整配置", open_at="2099-01-01T08:00:00Z", close_at="2099-01-01T10:00:00Z",
                            duration_minutes=90, entry_open_minutes=15, remind_minutes="30,10,5",
                            notice="# 须知\n诚信应考。", notice_ack_required=True, warn_unanswered=False)
        saved = client.post(url, headers=headers, json=full)
        assert saved.status_code == 201, saved.text
        body = saved.json()
        assert body["entry_open_minutes"] == 15 and body["remind_minutes"] == "30,10,5"
        assert body["notice_ack_required"] is True and body["warn_unanswered"] is False


def test_exam_url_masked_for_non_managers_and_reveal_writes_audit(tmp_path):
    """token 保留给能读的人，但取用必须留痕：列表只给打码串，完整地址走 reveal-url。

    覆盖两类「能读、不能管」的人：审核员，以及卷已转让给别人的原作者。
    留痕记的是「谁把地址拿走了」——所以断言落在 reveal 这个显式动作上，
    而不是落在列表读取上（列表每次翻页都调，按读取记会被正常操作淹掉）。
    """
    with admin_client(tmp_path) as client:
        db = client.app.state.session_factory()
        try:
            db.add(AdminUser(username="auditor", password_hash=password_hash.hash(PASSWORD), display_name="auditor", role="reviewer"))
            db.commit()
        finally:
            db.close()

        root = login(client)
        problem = approve_problem(client, root)
        question = {"problem_id_no": problem["problem_id_no"], "score": 100, "sort_order": 0}

        # 卷由 writer 建并发布——他此刻是负责人，完整地址内联给他。
        writer = login(client, "writer")
        paper = _published_paper(client, writer, [question])
        link = client.post(f"/api/admin/papers/{paper['id']}/links", headers=writer, json=link_payload(name="三班期中考")).json()
        owner_row = client.get("/api/admin/exam-links", headers=writer).json()["items"][0]
        assert "exam_url" in owner_row and "exam_url_hint" not in owner_row
        assert "copy" in owner_row["allowed_actions"] and "reveal_url" not in owner_row["allowed_actions"]
        token = owner_row["exam_url"].rsplit("/", 1)[-1]

        # 审核员：列表只给打码串，完整 token 在整个响应体里搜不到。
        auditor = login(client, "auditor")
        listing = client.get("/api/admin/exam-links", headers=auditor)
        assert token not in listing.text
        row = listing.json()["items"][0]
        assert "exam_url" not in row
        assert row["exam_url_hint"] == f"/exam/{token[:4]}…{token[-4:]}"
        assert row["allowed_actions"] == ["view", "reveal_url"]

        # 取用：拿得到完整地址，且落一条审计。
        revealed = client.post(f"/api/admin/links/{link['id']}/reveal-url", headers=auditor)
        assert revealed.status_code == 200, revealed.text
        assert revealed.json()["exam_url"].endswith(f"/exam/{token}")
        trail = client.get(f"/api/admin/papers/{paper['id']}/audit", headers=auditor).json()["items"]
        event = next(item for item in trail if item["event"] == "admin_paper_link_reveal_url")
        assert event["by"]["display_name"] == "auditor"
        assert event["summary"]["link_id"] == link["id"] and event["summary"]["by_manager"] is False

        # 读不到这张卷的人：连打码串都没有，reveal 直接 403。
        stranger = login(client, "writer2")
        assert client.post(f"/api/admin/links/{link['id']}/reveal-url", headers=stranger).status_code == 403

        # 卷转让给 writer2 后，原作者 writer 仍能读（created_by），但同样只剩打码串。
        root = login(client)
        owners = client.get("/api/admin/paper-owners", headers=root).json()["items"]
        writer2_id = next(item["id"] for item in owners if item["display_name"] == "writer2")
        current = client.get(f"/api/admin/papers/{paper['id']}", headers=root).json()
        transferred = client.patch(f"/api/admin/papers/{paper['id']}/owner", headers=match(root, current["revision"]), json={"owner_id": writer2_id})
        assert transferred.status_code == 200, transferred.text

        writer = login(client, "writer")
        after = client.get(f"/api/admin/papers/{paper['id']}", headers=writer)
        assert after.status_code == 200 and token not in after.text
        author_link = after.json()["links"][0]
        assert "exam_url" not in author_link
        assert author_link["exam_url_hint"] == f"/exam/{token[:4]}…{token[-4:]}"
        assert author_link["allowed_actions"] == ["view", "reveal_url"]
