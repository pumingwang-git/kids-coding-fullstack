"""E6: 课程发布只在状态转换时创建新的发布代次。"""
from pathlib import Path

from test_admin_courses import add_lesson, add_section, create_category, create_course
from test_exam import admin_login, build_app


def _ready_course(tmp_path: Path):
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    category = create_category(client, headers).json()
    course = create_course(client, headers, category["id"]).json()
    section = add_section(client, headers, course["id"]).json()
    add_lesson(client, headers, section["id"])
    return client, headers, course["id"]


def test_publish_replay_is_idempotent_but_new_key_is_conflict(tmp_path: Path):
    client, headers, course_id = _ready_course(tmp_path)
    first_headers = {**headers, "Idempotency-Key": "course-publish-1"}

    first = client.post(f"/api/admin/courses/{course_id}/publish", headers=first_headers)
    assert first.status_code == 200, first.text
    assert first.json()["publish_generation"] == 1

    replay = client.post(f"/api/admin/courses/{course_id}/publish", headers=first_headers)
    assert replay.status_code == 200, replay.text
    assert replay.json() == {
        "id": course_id,
        "status": "published",
        "idempotent": True,
        "publish_generation": 1,
        "hints": [],
    }

    duplicate = client.post(
        f"/api/admin/courses/{course_id}/publish",
        headers={**headers, "Idempotency-Key": "course-publish-2"},
    )
    assert duplicate.status_code == 409
    assert client.get(f"/api/admin/courses/{course_id}", headers=headers).json()["status"] == "published"


def test_off_shelf_course_can_create_next_publish_generation(tmp_path: Path):
    client, headers, course_id = _ready_course(tmp_path)

    first = client.post(
        f"/api/admin/courses/{course_id}/publish",
        headers={**headers, "Idempotency-Key": "course-publish-1"},
    )
    assert first.status_code == 200, first.text
    assert client.post(f"/api/admin/courses/{course_id}/off-shelf", headers=headers).status_code == 200

    republished = client.post(
        f"/api/admin/courses/{course_id}/publish",
        headers={**headers, "Idempotency-Key": "course-publish-2"},
    )
    assert republished.status_code == 200, republished.text
    assert republished.json()["publish_generation"] == 2


def test_legacy_publish_without_key_still_works_once(tmp_path: Path):
    client, headers, course_id = _ready_course(tmp_path)

    first = client.post(f"/api/admin/courses/{course_id}/publish", headers=headers)
    assert first.status_code == 200, first.text
    assert first.json()["publish_generation"] == 1

    # Legacy callers get a generated key, so a second request cannot be
    # mistaken for a retry and is rejected by the published-state guard.
    second = client.post(f"/api/admin/courses/{course_id}/publish", headers=headers)
    assert second.status_code == 409, second.text
