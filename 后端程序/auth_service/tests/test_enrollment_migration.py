"""0056 enrollments migration: isolated SQLite round-trip and fail-closed rollback."""
from pathlib import Path

import pytest
import sqlalchemy as sa

from alembic import command
from alembic.config import Config
from app.config import get_settings
from app.models import Base

SERVICE_ROOT = Path(__file__).resolve().parents[1]
PREVIOUS_HEAD = "0055_class_groups"
ENROLLMENT_TABLE = "enrollments"


def alembic_config() -> Config:
    config = Config(str(SERVICE_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(SERVICE_ROOT / "alembic"))
    return config


@pytest.fixture
def migration_env(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'enrollments.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    engine = sa.create_engine(url)
    pre_enrollment_tables = [
        table for name, table in Base.metadata.tables.items() if name != ENROLLMENT_TABLE
    ]
    Base.metadata.create_all(engine, tables=pre_enrollment_tables)
    engine.dispose()
    config = alembic_config()
    command.stamp(config, PREVIOUS_HEAD)
    try:
        yield config, url
    finally:
        get_settings.cache_clear()


def table_names(url: str) -> set[str]:
    engine = sa.create_engine(url)
    try:
        return set(sa.inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_upgrade_and_empty_downgrade_are_repeatable(migration_env):
    config, url = migration_env
    command.upgrade(config, "head")
    assert ENROLLMENT_TABLE in table_names(url)
    command.downgrade(config, PREVIOUS_HEAD)
    assert ENROLLMENT_TABLE not in table_names(url)
    command.upgrade(config, "head")
    assert ENROLLMENT_TABLE in table_names(url)


def test_source_is_not_closed_by_a_database_check(migration_env):
    config, url = migration_env
    command.upgrade(config, "head")
    engine = sa.create_engine(url)
    try:
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO enrollments "
                    "(student_id, course_id, source, status) "
                    "VALUES (1, 1, 'class_batch', 'active')"
                )
            )
            conn.execute(
                sa.text(
                    "INSERT INTO enrollments "
                    "(student_id, course_id, source, status) "
                    "VALUES (1, 1, 'class_batch', 'active')"
                )
            )
    finally:
        engine.dispose()


def test_downgrade_refuses_business_data(migration_env):
    config, url = migration_env
    command.upgrade(config, "head")
    engine = sa.create_engine(url)
    try:
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO enrollments "
                    "(student_id, course_id, source, status) VALUES (1, 1, 'admin', 'active')"
                )
            )
    finally:
        engine.dispose()
    with pytest.raises(RuntimeError, match="enrollments"):
        command.downgrade(config, PREVIOUS_HEAD)
    assert ENROLLMENT_TABLE in table_names(url)
