import ast
from pathlib import Path

from sqlalchemy import select

from app.notification_links import (
    admin_help_request_link,
    announcement_link,
    course_link,
    exam_attempt_link,
    lesson_homework_link,
    parse_announcement_target,
    student_help_request_link,
)


from app.models import LessonBlockCompletion, User
from test_exam import build_app, student_login
from test_scratch import build_scratch_lesson


ROOT = Path(__file__).resolve().parents[3]
ROUTER = ROOT / "前端程序" / "study-blog-vue" / "src" / "router" / "index.js"
ADMIN_PUBLIC = ROOT / "前端程序" / "study-blog-vue" / "public" / "admin"


def _student_route_patterns() -> list[str]:
    import re

    return re.findall(r'path:\s*"([^"\n]+)"', ROUTER.read_text(encoding="utf-8"))


def _matches_route(link: str) -> bool:
    import re
    from urllib.parse import urlsplit

    path = urlsplit(link).path
    for pattern in _student_route_patterns():
        if pattern == "/:pathMatch(.*)*":
            continue
        expression = re.sub(r":\w+(?:\([^)]*\))?", r"[^/]+", pattern)
        if re.fullmatch(expression, path):
            return True
    return False


def test_notification_links_are_canonical_and_reachable():
    links = [lesson_homework_link(2, 3), exam_attempt_link("tok/with space"), student_help_request_link(4)]
    assert all(_matches_route(link) for link in links)
    admin_link = admin_help_request_link(4)
    assert admin_link.startswith("/admin/")
    assert (ADMIN_PUBLIC / admin_link.removeprefix("/admin/").split("?", 1)[0]).is_file()
    assert announcement_link("/courses/9") == "/courses/9"
    assert parse_announcement_target("/courses/9")["ids"] == ("9",)


def test_all_notification_link_call_sites_use_real_client_destinations():
    allowed_builders = {
        "course_link": lambda: course_link(1),
        "lesson_homework_link": lambda: lesson_homework_link(1, 1),
        "exam_attempt_link": lambda: exam_attempt_link("token"),
        "admin_help_request_link": lambda: admin_help_request_link(1),
        "student_help_request_link": lambda: student_help_request_link(1),
    }
    link_expressions = []
    for source in (ROOT / "后端程序" / "auth_service" / "app").rglob("*.py"):
        if source.name == "notification_service.py":
            continue
        tree = ast.parse(source.read_text(encoding="utf-8-sig"), filename=str(source))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or getattr(node.func, "id", None) != "create_notification":
                continue
            keyword = next((item for item in node.keywords if item.arg == "link_url"), None)
            assert keyword is not None, f"{source} 的 create_notification 缺少 link_url"
            if isinstance(keyword.value, ast.Call) and isinstance(keyword.value.func, ast.Name):
                link_expressions.append(keyword.value.func.id)
            elif isinstance(keyword.value, ast.Name):
                # `link` 由课时作业/考试来源分支赋值；其候选仍须是白名单构造器。
                assert keyword.value.id == "link" and source.name == "notification_reminders.py"
            elif isinstance(keyword.value, ast.Attribute):
                # 公告的输入在 Pydantic validator 中被 announcement_link() 重建。
                assert (keyword.value.value.id, keyword.value.attr) == ("payload", "link_url")
            else:
                raise AssertionError(f"{source} 的 link_url 不是受控构造器：{ast.unparse(keyword.value)}")
    assert set(link_expressions) == set(allowed_builders)
    for name, build in allowed_builders.items():
        link = build()
        if name == "admin_help_request_link":
            assert (ADMIN_PUBLIC / link.removeprefix("/admin/").split("?", 1)[0]).is_file()
        else:
            assert _matches_route(link), f"{name} 生成了不存在的学生路由：{link}"


def test_record_completion_duplicate_write_commits_other_pending_change(tmp_path):
    from app.routers.courses import _record_completion

    app = build_app(tmp_path)
    student_login(app)
    built = build_scratch_lesson(app)
    db = app.state.session_factory()
    try:
        user = db.scalar(select(User).where(User.username == "learner"))
        block = db.get(__import__("app.models", fromlist=["CourseLessonBlock"]).CourseLessonBlock, built["block_ids"][0])
        _record_completion(db, user, block, built["lesson_id"], "manual", set(), commit=True)
        user.status = "completion-committed"
        _record_completion(db, user, block, built["lesson_id"], "manual", set(), commit=True)
    finally:
        db.close()
    check = app.state.session_factory()
    try:
        assert check.scalar(select(User.status).where(User.username == "learner")) == "completion-committed"
        assert len(check.scalars(select(LessonBlockCompletion).where(
            LessonBlockCompletion.block_id == built["block_ids"][0])).all()) == 1
    finally:
        check.close()


def test_record_completion_can_join_outer_transaction(tmp_path):
    from app.models import CourseLessonBlock
    from app.routers.courses import _record_completion

    app = build_app(tmp_path)
    student_login(app)
    built = build_scratch_lesson(app)
    db = app.state.session_factory()
    try:
        user = db.scalar(select(User).where(User.username == "learner"))
        block = db.get(CourseLessonBlock, built["block_ids"][0])
        user.status = "outer-transaction"
        _record_completion(db, user, block, built["lesson_id"], "manual", set(), commit=False)
        db.commit()
    finally:
        db.close()
    check = app.state.session_factory()
    try:
        assert check.scalar(select(User.status).where(User.username == "learner")) == "outer-transaction"
        assert len(check.scalars(select(LessonBlockCompletion).where(
            LessonBlockCompletion.block_id == built["block_ids"][0])).all()) == 1
    finally:
        check.close()
