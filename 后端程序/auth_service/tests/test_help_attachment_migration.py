from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from app.config import get_settings

SERVICE_ROOT = Path(__file__).resolve().parents[1]


def test_0078_creates_private_attachment_and_read_tables(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'help-attachments.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    config = Config(str(SERVICE_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(SERVICE_ROOT / "alembic"))
    command.upgrade(config, "0078_help_attachments_and_reads")
    engine = sa.create_engine(url)
    try:
        inspector = sa.inspect(engine)
        tables = set(inspector.get_table_names())
        assert {"help_message_attachments", "help_chat_line_reads"} <= tables
        columns = {item["name"] for item in inspector.get_columns("help_message_attachments")}
        assert {"storage_key", "uploaded_by_user_id", "uploaded_by_admin_user_id", "purged_at"} <= columns
        checks = {item["name"] for item in inspector.get_check_constraints("help_message_attachments")}
        assert "ck_help_attachments_one_uploader" in checks
    finally:
        engine.dispose()
        get_settings.cache_clear()
