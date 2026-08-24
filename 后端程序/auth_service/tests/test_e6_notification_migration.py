"""E6 notification migration chain must be exercised revision by revision."""

from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from app.config import get_settings
from app.models import Base

SERVICE_ROOT = Path(__file__).resolve().parents[1]
# The migration filename contains ``orphaned``, while its declared Alembic
# revision (and 0062's down_revision) is the shorter identifier.
BASE_REVISION = "0061_revoke_class_enrollments"
REVISIONS = (
    "0062_notifications_foundation",
    "0063_help_requests",
    "0064_course_publish_generation",
    "0065_scratch_review_revision",
    "0066_help_request_hashes",
    "0067_scratch_review_idempotency",
)


def alembic_config() -> Config:
    config = Config(str(SERVICE_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(SERVICE_ROOT / "alembic"))
    return config


def _prepare_0061_schema(engine: sa.Engine) -> None:
    """Undo only post-0061 objects from the current ORM metadata."""
    with engine.begin() as conn:
        for table in ("notification_receipts", "notifications", "help_messages", "help_requests"):
            conn.exec_driver_sql(f'DROP TABLE IF EXISTS "{table}"')
        for table, columns in {
            "courses": (
                "publish_generation",
                "last_publish_idempotency_key_hash",
                "last_publish_request_hash",
            ),
            "scratch_submissions": (
                "review_revision",
                "last_review_idempotency_key_hash",
                "last_review_request_hash",
            ),
        }.items():
            for column in columns:
                conn.exec_driver_sql(f'ALTER TABLE "{table}" DROP COLUMN "{column}"')


@pytest.fixture
def migration_env(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'e6-migrations.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    engine = sa.create_engine(url)
    try:
        Base.metadata.create_all(engine)
        _prepare_0061_schema(engine)
        config = alembic_config()
        command.stamp(config, BASE_REVISION)
        yield config, url
    finally:
        engine.dispose()
        get_settings.cache_clear()


def _version(url: str) -> str:
    engine = sa.create_engine(url)
    try:
        with engine.connect() as conn:
            return conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
    finally:
        engine.dispose()


def _columns(url: str, table: str) -> set[str]:
    engine = sa.create_engine(url)
    try:
        return {column["name"] for column in sa.inspect(engine).get_columns(table)}
    finally:
        engine.dispose()


def _tables(url: str) -> set[str]:
    engine = sa.create_engine(url)
    try:
        return set(sa.inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_e6_migrations_upgrade_one_revision_at_a_time(migration_env):
    config, url = migration_env
    assert _version(url) == BASE_REVISION

    command.upgrade(config, "0062_notifications_foundation")
    assert _version(url) == REVISIONS[0]
    assert {"notifications", "notification_receipts"} <= _tables(url)

    command.upgrade(config, "0063_help_requests")
    assert _version(url) == REVISIONS[1]
    assert {"help_requests", "help_messages"} <= _tables(url)

    command.upgrade(config, "0064_course_publish_generation")
    assert _version(url) == REVISIONS[2]
    assert {"publish_generation", "last_publish_idempotency_key_hash", "last_publish_request_hash"} <= _columns(
        url, "courses"
    )

    command.upgrade(config, "0065_scratch_review_revision")
    assert _version(url) == REVISIONS[3]
    assert "review_revision" in _columns(url, "scratch_submissions")

    command.upgrade(config, "0066_help_request_hashes")
    assert _version(url) == REVISIONS[4]
    assert "request_hash" in _columns(url, "help_requests")
    assert "request_hash" in _columns(url, "help_messages")

    command.upgrade(config, "0067_scratch_review_idempotency")
    assert _version(url) == REVISIONS[5]
    assert {
        "last_review_idempotency_key_hash",
        "last_review_request_hash",
    } <= _columns(url, "scratch_submissions")
