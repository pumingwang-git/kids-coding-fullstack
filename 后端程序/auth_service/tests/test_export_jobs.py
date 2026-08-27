"""T6 regression guards for execution-time authorization."""
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import select
from test_admin_classes import login_as_role, seed_course
from test_exam import admin_login, build_app

from app.models import AuditEvent, ClassTeacher, ExportJob
from app.tasks import exports


def test_export_worker_recomputes_scope_in_worker_not_request_snapshot():
    source = (Path(__file__).parents[1] / "app" / "tasks" / "exports.py").read_text(encoding="utf-8")
    assert "visible_class_ids(admin, db)" in source
    assert "exportable_class_ids(admin, db)" in source
    assert "requested_by" in source
    assert "class_id not in export_ids" in source


def test_admin_download_polls_accepted_export_jobs():
    source = (
        Path(__file__).parents[3] / "前端程序" / "study-blog-vue" / "public" / "admin" / "admin-api.js"
    ).read_text(encoding="utf-8")
    assert "response.status === 202" in source
    assert "/classes/export-jobs/" in source
    assert "status?.status === \"failed\"" in source
    assert "status.error || \"导出任务失败。\"" in source
    assert "导出任务等待超时，请稍后重试。" in source
    assert "attempt < 160" in source


def test_export_worker_logs_scope_denial_after_teacher_is_removed(tmp_path: Path, monkeypatch, caplog):
    app = build_app(tmp_path)
    manager, manager_headers = admin_login(app)
    course_id = seed_course(app)
    class_response = manager.post(
        "/api/admin/classes", headers=manager_headers,
        json={"name": "T6 卸任后导出", "course_id": course_id},
    )
    assert class_response.status_code == 201, class_response.text
    class_id = class_response.json()["id"]
    login_as_role(app, "teacher", admin_id=901)

    db = app.state.session_factory()
    try:
        db.add(ClassTeacher(class_id=class_id, admin_user_id=901, role_in_class="teacher"))
        db.flush()
        job = ExportJob(
            requested_by=901, export_type="class_insight", params={"class_id": class_id},
        )
        db.add(job)
        db.commit()
        job_id = job.id

        assignment = db.scalar(select(ClassTeacher).where(
            ClassTeacher.class_id == class_id, ClassTeacher.admin_user_id == 901,
        ))
        assignment.ended_at = datetime.now(UTC)
        db.commit()
    finally:
        db.close()

    monkeypatch.setattr(exports, "get_settings", lambda: app.state.settings)
    with caplog.at_level("WARNING", logger="app.permissions"):
        with pytest.raises(PermissionError, match="已无该班级导出权限"):
            exports.run_export_job.run(job_id)

    db = app.state.session_factory()
    try:
        job = db.get(ExportJob, job_id)
        assert job.status == "failed"
        assert any(
            record.getMessage().startswith(
                f"scope_denied role=teacher admin_user_id=901 resource=class_group:{class_id}"
            )
            for record in caplog.records
        )
        assert list(db.scalars(select(AuditEvent).where(
            AuditEvent.event_type == "admin_export_download"
        ))) == []
    finally:
        db.close()


def test_export_worker_rechecks_capability_before_recomputing_scope(tmp_path: Path, monkeypatch, caplog):
    app = build_app(tmp_path)
    login_as_role(app, "editor", admin_id=902)
    db = app.state.session_factory()
    try:
        job = ExportJob(requested_by=902, export_type="class_relationships", params={})
        db.add(job)
        db.commit()
        job_id = job.id
    finally:
        db.close()

    monkeypatch.setattr(exports, "get_settings", lambda: app.state.settings)
    with caplog.at_level("WARNING", logger="app.permissions"):
        exports.run_export_job.run(job_id)

    db = app.state.session_factory()
    try:
        job = db.get(ExportJob, job_id)
        assert (job.status, job.error) == ("failed", "执行时管理员已无该导出权限")
        assert not caplog.records
        assert list(db.scalars(select(AuditEvent).where(
            AuditEvent.event_type == "admin_export_download"
        ))) == []
    finally:
        db.close()
