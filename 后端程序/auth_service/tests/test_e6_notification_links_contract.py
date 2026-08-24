from app.notification_links import (
    admin_help_request_link,
    announcement_link,
    exam_attempt_link,
    lesson_homework_link,
    parse_announcement_target,
    student_help_request_link,
)


def test_notification_links_are_canonical_and_reachable():
    assert lesson_homework_link(2, 3) == "/learn/2/homework/3"
    assert exam_attempt_link("tok/with space") == "/exam/tok%2Fwith%20space"
    assert student_help_request_link(4) == "/notifications"
    assert admin_help_request_link(4) == "/admin/notifications.html"
    assert announcement_link("/courses/9") == "/courses/9"
    assert parse_announcement_target("/courses/9")["ids"] == ("9",)


def test_record_completion_supports_outer_transaction_without_forcing_commit():
    from inspect import signature
    from app.routers.courses import _record_completion

    assert "commit" in signature(_record_completion).parameters
    assert signature(_record_completion).parameters["commit"].default is True
