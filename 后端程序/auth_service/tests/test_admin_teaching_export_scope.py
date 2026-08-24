"""D-E8 authorization guards for the class-insight CSV export."""

import json
from pathlib import Path

from sqlalchemy import select
from test_admin_classes import login_as_role, seed_course
from test_exam import admin_login, build_app

from app.models import AuditEvent, ClassTeacher


def _class_id(client, headers, app, name: str) -> int:
    response = client.post(
        "/api/admin/classes",
        headers=headers,
        json={"name": name, "course_id": seed_course(app)},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _add_assignment(app, class_id: int, admin_user_id: int, role: str) -> None:
    db = app.state.session_factory()
    try:
        db.add(ClassTeacher(class_id=class_id, admin_user_id=admin_user_id, role_in_class=role))
        db.commit()
    finally:
        db.close()


def _export_events(app, class_id: int | None = None) -> list[AuditEvent]:
    db = app.state.session_factory()
    try:
        statement = select(AuditEvent).where(AuditEvent.event_type == "admin_export_download")
        if class_id is not None:
            statement = statement.where(
                AuditEvent.resource_type == "class_insight_export",
                AuditEvent.resource_id == class_id,
            )
        return list(db.scalars(statement.order_by(AuditEvent.id)).all())
    finally:
        db.close()


def test_teacher_export_is_allowed_and_zero_rows_are_audited(tmp_path: Path):
    app = build_app(tmp_path)
    manager, manager_headers = admin_login(app)
    class_id = _class_id(manager, manager_headers, app, "D-E8 空班")
    teacher, teacher_headers = login_as_role(app, "teacher", admin_id=801)
    _add_assignment(app, class_id, 801, "teacher")

    overview = teacher.get(
        f"/api/admin/teaching/classes/{class_id}/overview", headers=teacher_headers
    )
    assert overview.status_code == 200
    assert overview.json()["capabilities"] == {"export_class_insight": True}

    response = teacher.get(
        f"/api/admin/teaching/classes/{class_id}/export", headers=teacher_headers
    )
    assert response.status_code == 200
    events = _export_events(app, class_id)
    assert len(events) == 1
    assert json.loads(events[0].summary_json)["row_count"] == 0


def test_assistant_export_is_scope_denied_without_audit_and_matches_missing(
    tmp_path: Path, caplog,
):
    app = build_app(tmp_path)
    manager, manager_headers = admin_login(app)
    class_id = _class_id(manager, manager_headers, app, "D-E8 助教班")
    assistant, assistant_headers = login_as_role(app, "assistant", admin_id=802)
    _add_assignment(app, class_id, 802, "assistant")

    with caplog.at_level("WARNING", logger="app.permissions"):
        denied = assistant.get(
            f"/api/admin/teaching/classes/{class_id}/export", headers=assistant_headers
        )
        missing = assistant.get(
            "/api/admin/teaching/classes/99999/export", headers=assistant_headers
        )
    assert denied.status_code == missing.status_code == 404
    assert denied.json() == missing.json() == {"detail": "班级不存在。"}
    assert caplog.text.count("scope_denied") == 2
    assert f"resource=class_group:{class_id}" in caplog.text
    assert _export_events(app) == []

    overview = assistant.get(
        f"/api/admin/teaching/classes/{class_id}/overview", headers=assistant_headers
    )
    assert overview.status_code == 200
    assert overview.json()["capabilities"] == {"export_class_insight": False}


def test_teacher_assistant_scope_denial_does_not_block_teacher_class_export(
    tmp_path: Path,
):
    app = build_app(tmp_path)
    manager, manager_headers = admin_login(app)
    assistant_class = _class_id(manager, manager_headers, app, "D-E8 助教关系")
    teacher_class = _class_id(manager, manager_headers, app, "D-E8 主任关系")
    teacher, teacher_headers = login_as_role(app, "teacher", admin_id=803)
    _add_assignment(app, assistant_class, 803, "assistant")
    _add_assignment(app, teacher_class, 803, "teacher")

    denied = teacher.get(
        f"/api/admin/teaching/classes/{assistant_class}/export", headers=teacher_headers
    )
    allowed = teacher.get(
        f"/api/admin/teaching/classes/{teacher_class}/export", headers=teacher_headers
    )
    assert denied.status_code == 404
    assert allowed.status_code == 200
    assert len(_export_events(app, teacher_class)) == 1
    assert len(_export_events(app)) == 1


def test_content_roles_hit_export_feature_gate(tmp_path: Path):
    app = build_app(tmp_path)
    manager, manager_headers = admin_login(app)
    class_id = _class_id(manager, manager_headers, app, "D-E8 功能闸")
    for index, role in enumerate(("editor", "reviewer"), start=810):
        client, headers = login_as_role(app, role, admin_id=index)
        denied = client.get(
            f"/api/admin/teaching/classes/{class_id}/export", headers=headers
        )
        missing = client.get(
            "/api/admin/teaching/classes/99999/export", headers=headers
        )
        assert denied.status_code == missing.status_code == 403
    assert _export_events(app) == []
