"""G6 migration contract for the exam assignment roster."""

from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.models import Base

SERVICE_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_FILE = SERVICE_ROOT / "alembic" / "versions" / "0059_exam_assignments.py"
TABLE = "exam_assignments"
PREVIOUS_HEAD = "0058_enrollment_class_source"
# Pin the migration under test: "head" currently resolves to 0059, masking this bug.
EXAM_ASSIGNMENT_REVISION = "0059_exam_assignments"


def alembic_config() -> Config:
    config = Config(str(SERVICE_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(SERVICE_ROOT / "alembic"))
    return config


@pytest.fixture
def migration_env(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'migration.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    engine = sa.create_engine(url)
    pre_roster_tables = [table for name, table in Base.metadata.tables.items() if name != TABLE]
    Base.metadata.create_all(engine, tables=pre_roster_tables)
    engine.dispose()
    config = alembic_config()
    command.stamp(config, PREVIOUS_HEAD)
    try:
        yield config, url
    finally:
        get_settings.cache_clear()


def execute(url: str, statement: str) -> None:
    engine = sa.create_engine(url)
    try:
        with engine.begin() as conn:
            conn.execute(sa.text(statement))
    finally:
        engine.dispose()


def test_upgrade_and_empty_downgrade_round_trip(migration_env):
    config, url = migration_env
    command.upgrade(config, EXAM_ASSIGNMENT_REVISION)
    assert TABLE in sa.inspect(sa.create_engine(url)).get_table_names()
    command.downgrade(config, PREVIOUS_HEAD)
    assert TABLE not in sa.inspect(sa.create_engine(url)).get_table_names()


def test_active_assignment_is_unique_but_ended_history_can_be_reassigned(migration_env):
    config, url = migration_env
    command.upgrade(config, EXAM_ASSIGNMENT_REVISION)
    execute(url, "INSERT INTO exam_assignments (exam_link_id, target_type, target_id) VALUES (1, 'class', 7)")
    with pytest.raises(IntegrityError):
        execute(url, "INSERT INTO exam_assignments (exam_link_id, target_type, target_id) VALUES (1, 'class', 7)")
    execute(url, "UPDATE exam_assignments SET status = 'ended', ended_at = CURRENT_TIMESTAMP WHERE id = 1")
    execute(url, "INSERT INTO exam_assignments (exam_link_id, target_type, target_id) VALUES (1, 'class', 7)")
    engine = sa.create_engine(url)
    try:
        with engine.connect() as conn:
            assert conn.execute(sa.text("SELECT COUNT(*) FROM exam_assignments")).scalar() == 2
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("status", "ended_at"),
    [("active", "CURRENT_TIMESTAMP"), ("ended", "NULL")],
)
def test_status_and_ended_at_must_match(migration_env, status, ended_at):
    config, url = migration_env
    command.upgrade(config, EXAM_ASSIGNMENT_REVISION)
    with pytest.raises(IntegrityError):
        execute(
            url,
            "INSERT INTO exam_assignments "
            f"(exam_link_id, target_type, target_id, status, ended_at) "
            f"VALUES (1, 'student', 9, '{status}', {ended_at})",
        )


def test_downgrade_refuses_non_empty_table(migration_env):
    config, url = migration_env
    command.upgrade(config, EXAM_ASSIGNMENT_REVISION)
    execute(url, "INSERT INTO exam_assignments (exam_link_id, target_type, target_id) VALUES (1, 'student', 9)")
    with pytest.raises(RuntimeError):
        command.downgrade(config, PREVIOUS_HEAD)
    assert TABLE in sa.inspect(sa.create_engine(url)).get_table_names()


def test_model_and_migration_have_same_columns_indexes_and_checks(migration_env, tmp_path):
    config, url = migration_env
    command.upgrade(config, EXAM_ASSIGNMENT_REVISION)
    model_url = f"sqlite:///{tmp_path / 'model.db'}"
    model_engine = sa.create_engine(model_url)
    Base.metadata.create_all(model_engine)
    migrated = sa.inspect(sa.create_engine(url))
    model = sa.inspect(model_engine)
    assert [(c["name"], str(c["type"]), c["nullable"]) for c in model.get_columns(TABLE)] == [
        (c["name"], str(c["type"]), c["nullable"]) for c in migrated.get_columns(TABLE)
    ]
    assert sorted((i["name"], i["unique"], tuple(i["column_names"])) for i in model.get_indexes(TABLE)) == sorted(
        (i["name"], i["unique"], tuple(i["column_names"])) for i in migrated.get_indexes(TABLE)
    )
    assert sorted((c["name"], c["sqltext"]) for c in model.get_check_constraints(TABLE)) == sorted(
        (c["name"], c["sqltext"]) for c in migrated.get_check_constraints(TABLE)
    )


def test_migration_has_no_organisation_dimension_or_seed():
    source = MIGRATION_FILE.read_text(encoding="utf-8").lower()
    for banned in ("organization", "organisation", "tenant", "campus", "school_id"):
        assert banned not in source
    assert "bulk_insert" not in source
    assert "insert into" not in source
