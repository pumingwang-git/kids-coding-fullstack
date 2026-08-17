"""数学星球后端最小回归。"""
import tempfile
from pathlib import Path
from uuid import uuid4

from test_exam import build_app, scsrf, student_login


def _setup(username="mathlearner"):
    app = build_app(Path(tempfile.mkdtemp()))
    return student_login(app, username=username)


def _session(client_uuid=None, **overrides):
    item = {
        "client_uuid": client_uuid or str(uuid4()),
        "game_key": "game24",
        "mode": "challenge",
        "difficulty": "easy",
        "duration_sec": 60,
        "score": 30,
        "count_correct": 3,
        "count_wrong": 1,
        "max_combo": 2,
    }
    item.update(overrides)
    return item


def test_routes_registered():
    from app.main import app

    paths = app.openapi()["paths"]
    assert "/api/math-games/bootstrap" in paths
    assert "/api/math-games/sessions" in paths


def test_bootstrap_empty_and_aggregated_stats():
    client = _setup()
    assert client.get("/api/math-games/bootstrap").json()["stats"] == {
        "total_sessions": 0,
        "best_score": 0,
        "total_correct": 0,
        "total_wrong": 0,
        "best_combo": 0,
        "last_played_at": None,
    }
    items = [_session(score=20, count_correct=2), _session(score=50, count_correct=5, max_combo=4)]
    response = client.post("/api/math-games/sessions", headers=scsrf(client), json=items)
    assert response.status_code == 200, response.text
    stats = client.get("/api/math-games/bootstrap").json()["stats"]
    assert stats["total_sessions"] == 2
    assert stats["best_score"] == 50
    assert stats["total_correct"] == 7
    assert stats["total_wrong"] == 2
    assert stats["best_combo"] == 4
    assert stats["last_played_at"] is not None


def test_sessions_require_csrf_and_are_idempotent():
    client = _setup()
    item = _session()
    assert client.post("/api/math-games/sessions", json=[item]).status_code == 403
    response = client.post("/api/math-games/sessions", headers=scsrf(client), json=[item, item])
    assert response.json() == {"inserted": 1, "skipped": 1}
    response = client.post("/api/math-games/sessions", headers=scsrf(client), json=[item])
    assert response.json() == {"inserted": 0, "skipped": 1}


def test_sessions_validate_catalog_and_batch_limit():
    client = _setup()
    assert client.post(
        "/api/math-games/sessions",
        headers=scsrf(client),
        json=[_session(game_key="unknown")],
    ).status_code == 422
    assert client.post(
        "/api/math-games/sessions",
        headers=scsrf(client),
        json=[_session() for _ in range(51)],
    ).status_code == 422


def test_stats_are_isolated_by_student():
    first = _setup("mathstudent1")
    second = _setup("mathstudent2")
    first.post("/api/math-games/sessions", headers=scsrf(first), json=[_session(score=40)])
    assert first.get("/api/math-games/bootstrap").json()["stats"]["total_sessions"] == 1
    assert second.get("/api/math-games/bootstrap").json()["stats"]["total_sessions"] == 0
