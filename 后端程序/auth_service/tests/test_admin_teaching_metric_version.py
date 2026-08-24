"""T5 guards for stable learning-report metric provenance."""

import csv
import io
from pathlib import Path

from app.metric_versions import METRIC_VERSION
from app.models import ClassMember
from test_admin_classes import seed_course, seed_student
from test_exam import admin_login, build_app


def _seed_versioned_report(app, client, headers) -> int:
    response = client.post(
        "/api/admin/classes",
        headers=headers,
        json={"name": "T5 口径版本班", "course_id": seed_course(app)},
    )
    assert response.status_code == 201, response.text
    class_id = response.json()["id"]
    seed_student(app, 901)
    db = app.state.session_factory()
    try:
        db.add(ClassMember(class_id=class_id, student_id=901))
        db.commit()
    finally:
        db.close()
    return class_id


def test_metric_version_stays_pinned_until_the_metric_definition_changes():
    assert METRIC_VERSION == "v1"
    source = (
        Path(__file__).parents[1] / "app" / "routers" / "admin_teaching.py"
    ).read_text(encoding="utf-8")
    assert '"v1"' not in source
    assert source.count('"metric_version": METRIC_VERSION') == 6


def test_six_learning_reports_and_csv_share_metric_version(tmp_path: Path):
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    class_id = _seed_versioned_report(app, client, headers)
    paths = (
        f"/api/admin/teaching/classes/{class_id}/overview",
        f"/api/admin/teaching/classes/{class_id}/students",
        f"/api/admin/teaching/classes/{class_id}/homework",
        f"/api/admin/teaching/classes/{class_id}/exams",
        "/api/admin/teaching/review-queue",
        f"/api/admin/teaching/classes/{class_id}/weak-items",
    )
    for path in paths:
        response = client.get(path, headers=headers)
        assert response.status_code == 200, f"{path}: {response.text}"
        assert response.json()["metric_version"] == METRIC_VERSION

    exported = client.get(
        f"/api/admin/teaching/classes/{class_id}/export", headers=headers
    )
    assert exported.status_code == 200
    rows = list(csv.DictReader(io.StringIO(exported.content.decode("utf-8-sig"))))
    assert rows and rows[0]["metric_version"] == METRIC_VERSION
