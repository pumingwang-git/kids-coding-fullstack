"""E7 audit index migration is deliberately tested by revision, never head."""

from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from app.config import get_settings
from app.models import Base

ROOT = Path(__file__).resolve().parents[1]


def test_0069_created_at_index_upgrades_from_0068(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'audit-0069.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    engine = sa.create_engine(url)
    try:
        Base.metadata.create_all(engine)
        config = Config(str(ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(ROOT / "alembic"))
        command.stamp(config, "0068_help_request_lifecycle")
        command.upgrade(config, "0069_audit_events_created_idx")
        assert {item["name"] for item in sa.inspect(engine).get_indexes("audit_events")} >= {
            "ix_audit_events_created_at"
        }
    finally:
        engine.dispose()
        get_settings.cache_clear()
