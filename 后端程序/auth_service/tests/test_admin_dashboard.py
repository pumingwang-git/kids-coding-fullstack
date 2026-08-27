from pathlib import Path

from fastapi.testclient import TestClient
from app.metric_versions import METRIC_VERSION
from test_exam import admin_login, build_app


def test_dashboard_overview_is_one_authenticated_aggregate(tmp_path: Path):
    app = build_app(tmp_path)
    assert TestClient(app).get("/api/admin/dashboard/overview").status_code in {401, 403}
    client, headers = admin_login(app)
    response = client.get("/api/admin/dashboard/overview", headers=headers)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert set(payload) == {
        "metric_version", "server_now", "courses", "questions", "papers", "students",
        "exam_links", "course_access",
    }
    assert payload["metric_version"] == METRIC_VERSION
    assert set(payload["courses"]) == {"total", "published", "draft"}
    assert payload["courses"] == {"total": 0, "published": 0, "draft": 0}
    assert set(payload["questions"]) == {"draft", "pending", "approved"}
    assert payload["questions"] == {"draft": 0, "pending": 0, "approved": 0}
    assert set(payload["papers"]) == {"draft", "published", "archived"}
    assert payload["papers"] == {"draft": 0, "published": 0, "archived": 0}
    assert set(payload["students"]) == {"total"}
    assert payload["students"]["total"] == 0
    assert set(payload["exam_links"]) == {"active", "disabled", "all"}
    assert payload["exam_links"]["all"] == 0
    assert set(payload["course_access"]) == {"active_enrollments"}
    assert payload["course_access"]["active_enrollments"] == 0
    assert payload["server_now"]
