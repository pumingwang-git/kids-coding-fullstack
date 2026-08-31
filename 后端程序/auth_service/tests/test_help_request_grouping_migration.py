from pathlib import Path

import sqlalchemy as sa

from alembic import command
from alembic.config import Config
from app.config import get_settings

SERVICE_ROOT = Path(__file__).resolve().parents[1]
PREVIOUS_REVISION = "0074_help_chat_realtime"
TARGET_REVISION = "0075_help_request_grouping"


def _config() -> Config:
    config = Config(str(SERVICE_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(SERVICE_ROOT / "alembic"))
    return config


def _legacy_schema(conn) -> None:
    conn.execute(sa.text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
    conn.execute(sa.text("CREATE TABLE admin_users (id INTEGER PRIMARY KEY)"))
    conn.execute(sa.text("CREATE TABLE class_groups (id INTEGER PRIMARY KEY)"))
    conn.execute(
        sa.text(
            "CREATE TABLE help_chat_lines (id INTEGER PRIMARY KEY, class_id INTEGER NOT NULL, "
            "student_id INTEGER NOT NULL, last_message_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "
            "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, ended_at DATETIME)"
        )
    )
    conn.execute(
        sa.text(
            "CREATE UNIQUE INDEX uq_help_chat_lines_active ON help_chat_lines (class_id, student_id) "
            "WHERE ended_at IS NULL"
        )
    )
    conn.execute(
        sa.text(
            "CREATE TABLE help_requests (id INTEGER PRIMARY KEY, class_id INTEGER NOT NULL, "
            "student_id INTEGER NOT NULL, assigned_admin_user_id INTEGER, body TEXT NOT NULL, "
            "context_type VARCHAR(64) NOT NULL, context_id INTEGER, request_key_hash VARCHAR(128) NOT NULL, "
            "request_hash VARCHAR(128) NOT NULL, status VARCHAR(16) NOT NULL DEFAULT 'open', answered_at DATETIME, "
            "assignment_revision INTEGER NOT NULL DEFAULT 0, closed_at DATETIME, created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
    )
    conn.execute(
        sa.text(
            "CREATE TABLE help_messages (id INTEGER PRIMARY KEY, help_request_id INTEGER NOT NULL, "
            "sender_user_id INTEGER, sender_admin_user_id INTEGER, body TEXT NOT NULL, "
            "request_key_hash VARCHAR(128), request_hash VARCHAR(128), created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
    )


def _env(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'help-grouping.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    engine = sa.create_engine(url)
    with engine.begin() as conn:
        _legacy_schema(conn)
        conn.execute(sa.text("INSERT INTO users (id) VALUES (1)"))
        conn.execute(sa.text("INSERT INTO admin_users (id) VALUES (2)"))
        conn.execute(sa.text("INSERT INTO class_groups (id) VALUES (3)"))
    engine.dispose()
    command.stamp(_config(), PREVIOUS_REVISION)
    return url


def test_0075_backfills_line_group_and_first_message(tmp_path, monkeypatch):
    url = _env(tmp_path, monkeypatch)
    engine = sa.create_engine(url)
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO help_requests (id,class_id,student_id,assigned_admin_user_id,body,context_type,"
                "request_key_hash,request_hash) VALUES (10,3,1,2,'历史首问','general','k','h')"
            )
        )
    engine.dispose()

    command.upgrade(_config(), TARGET_REVISION)

    engine = sa.create_engine(url)
    try:
        with engine.connect() as conn:
            request = conn.execute(
                sa.text(
                    "SELECT chat_line_id, context_key, last_message_at FROM help_requests WHERE id=10"
                )
            ).one()
            message = conn.execute(
                sa.text("SELECT sender_user_id, body FROM help_messages WHERE help_request_id=10")
            ).one()
            line_count = conn.scalar(sa.text("SELECT count(*) FROM help_chat_lines"))
    finally:
        engine.dispose()
        get_settings.cache_clear()
    assert request.chat_line_id is not None
    assert request.context_key == "general"
    assert request.last_message_at is not None
    assert line_count == 1
    assert message == (1, "历史首问")


def test_0075_rejects_duplicate_contexts_and_reports_ids(tmp_path, monkeypatch):
    url = _env(tmp_path, monkeypatch)
    engine = sa.create_engine(url)
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO help_requests (id,class_id,student_id,assigned_admin_user_id,body,context_type,"
                "request_key_hash,request_hash) VALUES "
                "(10,3,1,2,'A','general','k1','h1'),(11,3,1,2,'B','general','k2','h2')"
            )
        )
    engine.dispose()

    try:
        command.upgrade(_config(), TARGET_REVISION)
    except RuntimeError as exc:
        assert "10" in str(exc) and "11" in str(exc)
        engine = sa.create_engine(url)
        try:
            columns = {item["name"] for item in sa.inspect(engine).get_columns("help_requests")}
            with engine.connect() as conn:
                assert conn.scalar(sa.text("SELECT count(*) FROM help_chat_lines")) == 0
        finally:
            engine.dispose()
        assert "chat_line_id" not in columns
    else:
        raise AssertionError("重复上下文必须让迁移失败")
    finally:
        get_settings.cache_clear()


def test_0075_does_not_duplicate_an_existing_first_message(tmp_path, monkeypatch):
    url = _env(tmp_path, monkeypatch)
    engine = sa.create_engine(url)
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO help_requests (id,class_id,student_id,assigned_admin_user_id,body,context_type,"
                "request_key_hash,request_hash,created_at) "
                "VALUES (10,3,1,2,'历史正文','general','k','h','2026-01-01 00:00:00')"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO help_messages (id,help_request_id,sender_user_id,body,request_key_hash,request_hash) "
                "VALUES (20,10,1,'已经存在的首条消息','mk','mh')"
            )
        )
        conn.execute(
            sa.text("UPDATE help_messages SET created_at='2026-01-02 00:00:00' WHERE id=20")
        )
    engine.dispose()

    command.upgrade(_config(), TARGET_REVISION)

    engine = sa.create_engine(url)
    try:
        with engine.connect() as conn:
            messages = (
                conn.execute(
                    sa.text("SELECT body FROM help_messages WHERE help_request_id=10 ORDER BY id")
                )
                .scalars()
                .all()
            )
            request_last = conn.scalar(
                sa.text("SELECT last_message_at FROM help_requests WHERE id=10")
            )
            line_last = conn.scalar(sa.text("SELECT last_message_at FROM help_chat_lines"))
    finally:
        engine.dispose()
        get_settings.cache_clear()
    assert messages == ["已经存在的首条消息"]
    assert str(request_last).startswith("2026-01-02 00:00:00")
    assert str(line_last).startswith("2026-01-02 00:00:00")


def test_0075_empty_database_can_round_trip(tmp_path, monkeypatch):
    url = _env(tmp_path, monkeypatch)
    command.upgrade(_config(), TARGET_REVISION)
    command.downgrade(_config(), PREVIOUS_REVISION)

    engine = sa.create_engine(url)
    try:
        columns = {item["name"] for item in sa.inspect(engine).get_columns("help_requests")}
    finally:
        engine.dispose()
        get_settings.cache_clear()
    assert "chat_line_id" not in columns
    assert "context_key" not in columns


def test_0075_nonempty_history_refuses_downgrade(tmp_path, monkeypatch):
    url = _env(tmp_path, monkeypatch)
    engine = sa.create_engine(url)
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO help_requests (id,class_id,student_id,assigned_admin_user_id,body,context_type,"
                "request_key_hash,request_hash) VALUES (10,3,1,2,'历史正文','general','k','h')"
            )
        )
    engine.dispose()
    command.upgrade(_config(), TARGET_REVISION)

    try:
        command.downgrade(_config(), PREVIOUS_REVISION)
    except RuntimeError as exc:
        assert "history is not empty" in str(exc)
    else:
        raise AssertionError("非空历史不得回滚删除分组字段")
    finally:
        get_settings.cache_clear()
