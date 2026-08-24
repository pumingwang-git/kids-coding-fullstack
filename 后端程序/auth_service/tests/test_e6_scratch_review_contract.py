"""E6 人工批改幂等与单事务契约。"""

from sqlalchemy import select

import app.routers.admin_scratch as admin_scratch
from app.models import AuditEvent, LessonBlockCompletion, Notification, ScratchSubmission
from test_admin_courses import reviewer_login
from test_scratch import (
    build_scratch_lesson,
    save_project,
    sb3_bytes,
    scratch_env,
    student_login,
    submit,
)


def _submitted(tmp_path):
    app = scratch_env(tmp_path)
    built = build_scratch_lesson(app)
    student = student_login(app)
    block_id = built["block_ids"][0]
    project_id = student.get(f"/api/scratch/lesson-blocks/{block_id}").json()["project"]["id"]
    save_project(student, project_id, sb3_bytes())
    submission_id = submit(student, block_id).json()["submission_id"]
    return app, built, submission_id, block_id


def test_review_idempotency_key_replays_without_revision_or_notification(tmp_path):
    app, built, submission_id, block_id = _submitted(tmp_path)
    headers = {**built["headers"], "Idempotency-Key": "review-once"}
    path = f"/api/admin/scratch/submissions/{submission_id}/review"
    first = built["client"].post(path, headers=headers, json={"verdict": "passed", "comment": "通过"})
    second = built["client"].post(path, headers=headers, json={"verdict": "passed", "comment": "通过"})
    assert first.status_code == second.status_code == 200
    assert second.json()["idempotent"] is True
    db = app.state.session_factory()
    try:
        row = db.get(ScratchSubmission, submission_id)
        assert row.review_revision == 1
        assert len(db.scalars(select(Notification).where(
            Notification.source_id == submission_id,
            Notification.kind == "homework_graded",
        )).all()) == 1
        assert len(db.scalars(select(LessonBlockCompletion).where(
            LessonBlockCompletion.block_id == block_id)).all()) == 1
    finally:
        db.close()


def test_review_key_cannot_be_reused_for_a_different_request(tmp_path):
    _, built, submission_id, _ = _submitted(tmp_path)
    headers = {**built["headers"], "Idempotency-Key": "review-conflict"}
    path = f"/api/admin/scratch/submissions/{submission_id}/review"
    assert built["client"].post(path, headers=headers, json={"verdict": "failed", "comment": "再试"}).status_code == 200
    conflict = built["client"].post(path, headers=headers, json={"verdict": "passed", "comment": "通过"})
    assert conflict.status_code == 409


def test_return_idempotency_key_replays_and_cross_action_conflicts(tmp_path):
    app, built, submission_id, _ = _submitted(tmp_path)
    headers = {**built["headers"], "Idempotency-Key": "return-once"}
    path = f"/api/admin/scratch/submissions/{submission_id}/return"
    assert built["client"].post(path, headers=headers, json={"comment": "请修改"}).status_code == 200
    replay = built["client"].post(path, headers=headers, json={"comment": "请修改"})
    assert replay.status_code == 200
    assert replay.json()["idempotent"] is True
    conflict = built["client"].post(
        f"/api/admin/scratch/submissions/{submission_id}/review", headers=headers,
        json={"verdict": "failed", "comment": "再试"},
    )
    assert conflict.status_code == 409
    db = app.state.session_factory()
    try:
        assert db.get(ScratchSubmission, submission_id).review_revision == 1
    finally:
        db.close()


def test_missing_review_key_returns_422_without_side_effects(tmp_path):
    app, built, submission_id, _ = _submitted(tmp_path)
    response = built["client"].post(
        f"/api/admin/scratch/submissions/{submission_id}/review",
        headers=built["headers"], json={"verdict": "passed", "comment": "通过"},
    )
    assert response.status_code == 422
    db = app.state.session_factory()
    try:
        row = db.get(ScratchSubmission, submission_id)
        assert row.review_revision == 0
        assert db.scalars(select(Notification).where(
            Notification.source_id == submission_id,
            Notification.source_type == "scratch_submission",
        )).all() == []
        assert db.scalars(select(AuditEvent).where(
            AuditEvent.resource_id == submission_id,
            AuditEvent.resource_type == "scratch_submission",
        )).all() == []
    finally:
        db.close()


def test_out_of_scope_submission_still_returns_404_before_missing_key(tmp_path, monkeypatch):
    app, built, submission_id, _ = _submitted(tmp_path)
    monkeypatch.setattr(admin_scratch, "visible_student_ids", lambda _admin, _db: set())
    response = built["client"].post(
        f"/api/admin/scratch/submissions/{submission_id}/review",
        headers=built["headers"], json={"verdict": "passed", "comment": "通过"},
    )
    assert response.status_code == 404


def test_unauthorized_role_still_returns_403_before_missing_key(tmp_path):
    app, _built, submission_id, _ = _submitted(tmp_path)
    reviewer, headers = reviewer_login(app)
    headers = {**headers, "X-CSRF-Token": reviewer.cookies.get("admin_csrf_token")}
    response = reviewer.post(
        f"/api/admin/scratch/submissions/{submission_id}/review",
        headers=headers, json={"verdict": "passed", "comment": "通过"},
    )
    assert response.status_code == 403
