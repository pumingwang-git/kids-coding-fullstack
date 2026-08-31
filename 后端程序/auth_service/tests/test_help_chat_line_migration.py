from pathlib import Path

import sqlalchemy as sa

from alembic import command
from alembic.config import Config
from app.config import get_settings
from app.routers.help_requests import _line_payload

SERVICE_ROOT = Path(__file__).resolve().parents[1]
PREVIOUS_REVISION = "0073_scratch_work_cover"
TARGET_REVISION = "0074_help_chat_realtime"


def _config() -> Config:
    config = Config(str(SERVICE_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(SERVICE_ROOT / "alembic"))
    return config


def test_0074_nonempty_chat_lines_refuse_downgrade(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'help-chat-lines.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    config = _config()
    command.upgrade(config, TARGET_REVISION)
    engine = sa.create_engine(url)
    with engine.begin() as conn:
        conn.execute(
            sa.text("INSERT INTO help_chat_lines (id,class_id,student_id) VALUES (1,999,999)")
        )
    engine.dispose()

    try:
        command.downgrade(config, PREVIOUS_REVISION)
    except RuntimeError as exc:
        assert "chat lines are not empty" in str(exc)
    else:
        raise AssertionError("非空聊天线不得被 0074 downgrade 删除")
    finally:
        engine = sa.create_engine(url)
        try:
            assert "help_chat_lines" in sa.inspect(engine).get_table_names()
        finally:
            engine.dispose()
            get_settings.cache_clear()


def test_line_payload_requires_explicit_admin_viewer():
    import inspect

    signature = inspect.signature(_line_payload)
    assert signature.parameters["viewer_admin_id"].default is None
    assert 'db.info.get("admin_user_id"' not in inspect.getsource(_line_payload)
