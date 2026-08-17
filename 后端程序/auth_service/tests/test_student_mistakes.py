"""学生错题本：自动归档、隔离与重做的最小回归。"""
from pathlib import Path

from test_exam import build_app, scsrf, student_login
from test_lesson_practice import answer, build_practice, seed_choice_problem


def _wrong_practice(client, app):
    problem_id_no = seed_choice_problem(app)["problem_id_no"]
    built = build_practice(app, problem_id_no=problem_id_no)
    response = answer(client, built["lesson_id"], built["block_ids"][-1], {"picked": "B"})
    assert response.status_code == 200, response.text
    return built


def test_wrong_lesson_answer_automatically_enters_mistake_book(tmp_path: Path):
    app = build_app(tmp_path)
    client = student_login(app, username="mistakelearner")
    _wrong_practice(client, app)

    listing = client.get("/api/student/mistakes")
    assert listing.status_code == 200, listing.text
    body = listing.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["source_type"] == "lesson_practice"
    assert item["status"] == "pending_review"
    assert item["can_review_here"] is True

    summary = client.get("/api/student/mistakes/summary").json()
    assert summary == {"total": 1, "due": 1, "mastered": 0, "recent_review_accuracy": None}


def test_review_updates_record_without_exposing_answer_in_detail(tmp_path: Path):
    app = build_app(tmp_path)
    client = student_login(app, username="reviewlearner")
    _wrong_practice(client, app)
    mistake_id = client.get("/api/student/mistakes").json()["items"][0]["id"]

    detail = client.get(f"/api/student/mistakes/{mistake_id}")
    assert detail.status_code == 200
    assert "analysis" not in detail.json()["question"]
    assert "correct" not in detail.json()["question"]

    reviewed = client.post(
        f"/api/student/mistakes/{mistake_id}/review", headers=scsrf(client),
        json={"answer": {"picked": "A"}},
    )
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["is_correct"] is True
    assert reviewed.json()["mastery_level"] == "basic"
    assert reviewed.json()["correct"] == {"labels": ["A"]}

    item = client.get("/api/student/mistakes").json()["items"][0]
    assert item["review_count"] == 1
    assert item["review_correct_count"] == 1


def test_mistakes_are_private_to_the_current_student(tmp_path: Path):
    app = build_app(tmp_path)
    owner = student_login(app, username="owner")
    _wrong_practice(owner, app)
    stranger = student_login(app, username="stranger")
    assert stranger.get("/api/student/mistakes").json()["total"] == 0
