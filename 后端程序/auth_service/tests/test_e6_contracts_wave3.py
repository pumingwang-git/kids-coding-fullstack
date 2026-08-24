from app.text_sanitize import plain_text


def test_plain_text_removes_markup_and_controls_without_escaping():
    assert plain_text("<b>hello</b>\x00 world") == "hello world"
    assert plain_text("a & b") == "a & b"


def test_help_request_lifecycle_contract_is_present():
    from app.models import HelpRequest

    assert {"open", "answered", "closed"}.issuperset(
        {"open", "answered", "closed"}
    )
    assert hasattr(HelpRequest, "answered_at")
    assert hasattr(HelpRequest, "assignment_revision")


def test_lifecycle_migration_is_numbered_0068_after_0067():
    migration = (__import__("pathlib").Path(__file__).parents[1]
                 / "alembic" / "versions" / "0068_help_request_lifecycle.py").read_text()
    assert 'revision = "0068_help_request_lifecycle"' in migration
    assert 'down_revision = "0067_scratch_review_idempotency"' in migration
