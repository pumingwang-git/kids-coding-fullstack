"""0073 封面列迁移的往返。

判据来源：《40、迁移回滚与种子数据规范》§3（建表/回滚顺序）、§6（测试落点）。

**整条迁移链在 SQLite 上跑不通**（`0008_admin_auth` 用 `op.add_column` 加外键，
SQLite 不支持 ALTER 约束），所以这里照 `test_class_migration.py` 的老办法：
`create_all` 建出 0072 时的库、`stamp` 到 0072，**只跑 0073 这一条**。
按纪律 `upgrade()` 的参数写死目标 revision，**永不 `upgrade("head")`**——
写 head 的话，将来任何一条新迁移出问题都会算到这个用例头上。

预置 0072 状态的方式是"建完再把列删掉"：`Base.metadata` 里已经有 `cover_key` 了，
`create_all` 建出来的表自带这一列，不删就等于在验一条什么都没干的迁移。
"""
from pathlib import Path

import pytest
import sqlalchemy as sa

from alembic import command
from alembic.config import Config
from app.config import get_settings
from app.models import Base

SERVICE_ROOT = Path(__file__).resolve().parents[1]
PREVIOUS_HEAD = "0072_dynamic_admin_rbac"
COVER_REVISION = "0073_scratch_work_cover"


def alembic_config() -> Config:
    config = Config(str(SERVICE_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(SERVICE_ROOT / "alembic"))
    return config


def columns(url: str, table: str) -> set[str]:
    engine = sa.create_engine(url)
    try:
        return {c["name"] for c in sa.inspect(engine).get_columns(table)}
    finally:
        engine.dispose()


@pytest.fixture
def migration_env(tmp_path, monkeypatch):
    """隔离的 SQLite 库，预置到 0072 的状态。

    必须走环境变量 + 清 lru_cache：`alembic/env.py` 会用 `get_settings().database_url`
    **覆盖** `sqlalchemy.url`，在 Config 上直接 set_main_option 无效，测试会跑到
    `.env` 里那个真实库上。
    """
    url = f"sqlite:///{tmp_path / 'migration.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()

    engine = sa.create_engine(url)
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(sa.text("ALTER TABLE scratch_works DROP COLUMN cover_key"))
    engine.dispose()

    config = alembic_config()
    command.stamp(config, PREVIOUS_HEAD)
    try:
        yield config, url
    finally:
        get_settings.cache_clear()


def test_upgrade_adds_cover_key_and_downgrade_removes_it(migration_env):
    config, url = migration_env
    assert "cover_key" not in columns(url, "scratch_works"), "预置的库不该已经有这一列"

    command.upgrade(config, COVER_REVISION)
    assert "cover_key" in columns(url, "scratch_works")

    command.downgrade(config, PREVIOUS_HEAD)
    assert "cover_key" not in columns(url, "scratch_works")


def test_existing_rows_survive_the_upgrade_with_null_cover(migration_env):
    """老作品必须原样留在表里，封面列为空——为空正是"发生成占位图"那条分支的入口。"""
    config, url = migration_env
    engine = sa.create_engine(url)
    with engine.begin() as conn:
        conn.execute(sa.text(
            "INSERT INTO users (id, username, email, hashed_password, status, failed_login_count)"
            " VALUES (1, 'alice', 'alice@example.com', 'x', 'active', 0)"
        ))
        conn.execute(sa.text(
            "INSERT INTO scratch_works (id, student_id, title, description, size_bytes,"
            " sprite_count, extensions_json, source, is_public, views)"
            " VALUES (1, 1, '老作品', '', 0, 0, '[]', 'free', 1, 0)"
        ))
    engine.dispose()

    command.upgrade(config, COVER_REVISION)

    engine = sa.create_engine(url)
    try:
        with engine.begin() as conn:
            row = conn.execute(sa.text(
                "SELECT title, cover_key FROM scratch_works WHERE id = 1"
            )).one()
    finally:
        engine.dispose()
    assert row.title == "老作品"
    assert row.cover_key is None
