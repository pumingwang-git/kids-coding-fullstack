"""E2 班级关系迁移的往返与 fail-closed 守卫。

判据来源：《40、迁移回滚与种子数据规范-2026-08-17》§2.1（禁组织字段）、§3（建表/回滚
顺序）、§5.1（迁移内禁业务种子）、§6（测试落点）。

§6 的第 5、6 条（种子幂等、生产拒绝）暂不适用：三张班级表全是业务数据，按 §5.1
迁移里没有也不允许有种子，班级种子脚本尚未存在。等脚本落地时在此补上。
"""
import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from app.config import get_settings
from app.models import Base

SERVICE_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_FILE = SERVICE_ROOT / "alembic" / "versions" / "0055_class_groups.py"
CLASS_TABLES = ("class_groups", "class_members", "class_teachers")
PREVIOUS_HEAD = "0054_math_games"
CLASS_REVISION = "0055_class_groups"


def alembic_config() -> Config:
    config = Config(str(SERVICE_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(SERVICE_ROOT / "alembic"))
    return config


@pytest.fixture
def migration_env(tmp_path, monkeypatch):
    """把迁移指向一个隔离的 SQLite 文件，并把库预置到 0054 的状态。

    两处坑：

    1. 必须走环境变量 + 清 lru_cache。``alembic/env.py`` 会用
       ``get_settings().database_url`` **覆盖** ``sqlalchemy.url``，在 Config 上
       直接 set_main_option 无效，测试会跑到 .env 里那个真实库上。
    2. **整条迁移链在 SQLite 上跑不通**：``0008_admin_auth`` 用 ``op.add_column``
       给 audit_events 加了外键，SQLite 不支持 ALTER 约束。本仓库的测试历来用
       ``Base.metadata.create_all`` 建库，迁移只在 PostgreSQL 上真正执行过。
       所以这里用 models 建出 0054 时的库再 stamp，只跑 0055——那正是要验的一条。
       全链验证靠 §6.7 的 PostgreSQL 用例。
    """
    url = f"sqlite:///{tmp_path / 'migration.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()

    # 只预置 0055 之前的表；班级表虽已进入 models，仍必须由 0055 创建。
    engine = sa.create_engine(url)
    pre_class_tables = [
        table for name, table in Base.metadata.tables.items() if name not in CLASS_TABLES
    ]
    Base.metadata.create_all(engine, tables=pre_class_tables)
    engine.dispose()

    config = alembic_config()
    command.stamp(config, PREVIOUS_HEAD)
    try:
        yield config, url
    finally:
        # 别把临时库的设置留给后面的用例。
        get_settings.cache_clear()


def table_names(url: str) -> set[str]:
    engine = sa.create_engine(url)
    try:
        return set(sa.inspect(engine).get_table_names())
    finally:
        engine.dispose()


def execute(url: str, statement: str) -> None:
    engine = sa.create_engine(url)
    try:
        with engine.begin() as conn:
            conn.execute(sa.text(statement))
    finally:
        engine.dispose()


# ==================== §6.1 / §6.2 / §6.3 往返 ====================


def test_upgrade_creates_the_three_class_tables(migration_env):
    config, url = migration_env
    command.upgrade(config, CLASS_REVISION)
    assert set(CLASS_TABLES) <= table_names(url)


def test_empty_downgrade_removes_them_and_upgrade_stays_repeatable(migration_env):
    config, url = migration_env
    command.upgrade(config, CLASS_REVISION)

    command.downgrade(config, PREVIOUS_HEAD)
    assert not (set(CLASS_TABLES) & table_names(url))

    # 再升一次：回滚若残留索引或约束，这一步会因重复创建而报错。
    command.upgrade(config, CLASS_REVISION)
    assert set(CLASS_TABLES) <= table_names(url)


# ==================== §2.3 班级关系唯一性与状态一致性 ====================


def prepare_class(url: str) -> None:
    execute(url, "INSERT INTO class_groups (name, course_id) VALUES ('三年级 A 班', 1)")


def test_active_member_is_unique_per_class_and_student(migration_env):
    config, url = migration_env
    command.upgrade(config, CLASS_REVISION)
    prepare_class(url)

    execute(url, "INSERT INTO class_members (class_id, student_id) VALUES (1, 1)")
    with pytest.raises(IntegrityError):
        execute(url, "INSERT INTO class_members (class_id, student_id) VALUES (1, 1)")


def test_student_can_rejoin_after_old_membership_is_left(migration_env):
    config, url = migration_env
    command.upgrade(config, CLASS_REVISION)
    prepare_class(url)

    execute(
        url,
        "INSERT INTO class_members (class_id, student_id, joined_at) "
        "VALUES (1, 1, '2026-08-01 09:00:00')",
    )
    execute(
        url,
        "UPDATE class_members SET status = 'left', left_at = '2026-08-02 09:00:00' WHERE id = 1",
    )
    execute(
        url,
        "INSERT INTO class_members (class_id, student_id, joined_at) "
        "VALUES (1, 1, '2026-08-03 09:00:00')",
    )

    engine = sa.create_engine(url)
    try:
        with engine.connect() as conn:
            assert conn.execute(sa.text("SELECT COUNT(*) FROM class_members")).scalar() == 2
    finally:
        engine.dispose()


def test_active_teacher_assignment_is_unique_per_class_and_admin(migration_env):
    config, url = migration_env
    command.upgrade(config, CLASS_REVISION)
    prepare_class(url)

    execute(
        url,
        "INSERT INTO class_teachers (class_id, admin_user_id, role_in_class) "
        "VALUES (1, 7, 'teacher')",
    )
    with pytest.raises(IntegrityError):
        execute(
            url,
            "INSERT INTO class_teachers (class_id, admin_user_id, role_in_class) "
            "VALUES (1, 7, 'teacher')",
        )


def test_teacher_cannot_also_be_active_assistant_in_same_class(migration_env):
    config, url = migration_env
    command.upgrade(config, CLASS_REVISION)
    prepare_class(url)

    execute(
        url,
        "INSERT INTO class_teachers (class_id, admin_user_id, role_in_class) "
        "VALUES (1, 7, 'teacher')",
    )
    with pytest.raises(IntegrityError):
        execute(
            url,
            "INSERT INTO class_teachers (class_id, admin_user_id, role_in_class) "
            "VALUES (1, 7, 'assistant')",
        )


def test_admin_can_change_class_role_after_ending_old_assignment(migration_env):
    config, url = migration_env
    command.upgrade(config, CLASS_REVISION)
    prepare_class(url)

    execute(
        url,
        "INSERT INTO class_teachers "
        "(class_id, admin_user_id, role_in_class, assigned_at) "
        "VALUES (1, 7, 'teacher', '2026-08-01 09:00:00')",
    )
    execute(
        url,
        "UPDATE class_teachers SET ended_at = '2026-08-02 09:00:00' WHERE id = 1",
    )
    execute(
        url,
        "INSERT INTO class_teachers "
        "(class_id, admin_user_id, role_in_class, assigned_at) "
        "VALUES (1, 7, 'assistant', '2026-08-03 09:00:00')",
    )

    engine = sa.create_engine(url)
    try:
        with engine.connect() as conn:
            assert conn.execute(sa.text("SELECT COUNT(*) FROM class_teachers")).scalar() == 2
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("status", "left_at"),
    [("active", "'2026-08-02 09:00:00'"), ("left", "NULL")],
)
def test_member_status_and_left_at_must_match(migration_env, status, left_at):
    config, url = migration_env
    command.upgrade(config, CLASS_REVISION)
    prepare_class(url)

    with pytest.raises(IntegrityError):
        execute(
            url,
            "INSERT INTO class_members (class_id, student_id, status, left_at) "
            f"VALUES (1, 1, '{status}', {left_at})",
        )


def test_models_match_migrated_class_table_structure(migration_env, tmp_path):
    config, migration_url = migration_env
    command.upgrade(config, CLASS_REVISION)

    model_url = f"sqlite:///{tmp_path / 'models.db'}"
    model_engine = sa.create_engine(model_url)
    try:
        Base.metadata.create_all(model_engine)
        migrated_engine = sa.create_engine(migration_url)
        try:
            for table_name in CLASS_TABLES:
                model = sa.inspect(model_engine)
                migrated = sa.inspect(migrated_engine)
                model_columns = [
                    (column["name"], str(column["type"]), column["nullable"])
                    for column in model.get_columns(table_name)
                ]
                migrated_columns = [
                    (column["name"], str(column["type"]), column["nullable"])
                    for column in migrated.get_columns(table_name)
                ]
                assert model_columns == migrated_columns

                model_indexes = sorted(
                    (index["name"], index["unique"], tuple(index["column_names"]))
                    for index in model.get_indexes(table_name)
                )
                migrated_indexes = sorted(
                    (index["name"], index["unique"], tuple(index["column_names"]))
                    for index in migrated.get_indexes(table_name)
                )
                assert model_indexes == migrated_indexes

                model_checks = sorted(
                    (check["name"], check["sqltext"])
                    for check in model.get_check_constraints(table_name)
                )
                migrated_checks = sorted(
                    (check["name"], check["sqltext"])
                    for check in migrated.get_check_constraints(table_name)
                )
                assert model_checks == migrated_checks
        finally:
            migrated_engine.dispose()
    finally:
        model_engine.dispose()


# ==================== §6.4 非空回滚必须被拒绝 ====================

# 逐表各测一次：只测其中一张，另外两张的守卫漏写也不会被发现。
NON_EMPTY_ROWS = {
    "class_groups": "INSERT INTO class_groups (name, course_id) VALUES ('三年级 A 班', 1)",
    "class_members": "INSERT INTO class_members (class_id, student_id) VALUES (1, 1)",
    "class_teachers": (
        "INSERT INTO class_teachers (class_id, admin_user_id, role_in_class) "
        "VALUES (1, 1, 'teacher')"
    ),
}


@pytest.mark.parametrize("table", CLASS_TABLES)
def test_downgrade_refuses_and_keeps_everything_when_a_table_has_data(migration_env, table):
    config, url = migration_env
    command.upgrade(config, CLASS_REVISION)
    execute(url, NON_EMPTY_ROWS[table])

    with pytest.raises(RuntimeError) as exc_info:
        command.downgrade(config, PREVIOUS_HEAD)

    assert table in str(exc_info.value)
    # 只断言抛错不够：必须确认三张表一张都没被删，数据也还在。
    assert set(CLASS_TABLES) <= table_names(url)
    engine = sa.create_engine(url)
    try:
        with engine.connect() as conn:
            assert conn.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar() == 1
    finally:
        engine.dispose()


# ==================== 当前有效关系唯一性 ====================


def test_active_member_and_teacher_relationships_are_unique(migration_env):
    """历史关系可保留，但同一时刻不能重复入班或重复带班。"""
    config, url = migration_env
    command.upgrade(config, CLASS_REVISION)
    execute(url, "INSERT INTO class_groups (id, name, course_id) VALUES (1, '三年级 A 班', 1)")

    execute(url, "INSERT INTO class_members (class_id, student_id) VALUES (1, 1)")
    with pytest.raises(sa.exc.IntegrityError):
        execute(url, "INSERT INTO class_members (class_id, student_id) VALUES (1, 1)")
    execute(url, "UPDATE class_members SET status = 'left', left_at = CURRENT_TIMESTAMP WHERE id = 1")
    execute(url, "INSERT INTO class_members (class_id, student_id) VALUES (1, 1)")

    execute(
        url,
        "INSERT INTO class_teachers (class_id, admin_user_id, role_in_class) VALUES (1, 1, 'teacher')",
    )
    with pytest.raises(sa.exc.IntegrityError):
        execute(
            url,
            "INSERT INTO class_teachers (class_id, admin_user_id, role_in_class) VALUES (1, 1, 'assistant')",
        )
    execute(url, "UPDATE class_teachers SET ended_at = CURRENT_TIMESTAMP WHERE id = 1")
    execute(
        url,
        "INSERT INTO class_teachers (class_id, admin_user_id, role_in_class) VALUES (1, 1, 'assistant')",
    )


# ==================== 迁移内容的静态守卫 ====================


def test_migration_carries_no_organisation_dimension():
    """§2.1：ADR-002 已裁决本期不预留多组织维度，空列也不行。"""
    source = MIGRATION_FILE.read_text(encoding="utf-8").lower()
    for banned in ("organization", "organisation", "tenant", "campus", "school_id"):
        assert banned not in source, f"迁移里出现了组织维度字段：{banned}"


def test_migration_writes_no_business_seed():
    """§5.1：三张表全是业务数据，迁移里不得有任何写入。"""
    source = MIGRATION_FILE.read_text(encoding="utf-8")
    assert "bulk_insert" not in source
    assert "INSERT INTO" not in source.upper()


def test_migration_chain_stays_single_headed():
    heads = ScriptDirectory.from_config(alembic_config()).get_heads()
    assert len(heads) == 1, f"迁移链出现分支：{heads}"


# ==================== §6.7 PostgreSQL ====================


@pytest.mark.skipif(
    not os.getenv("MIGRATION_TEST_POSTGRES_URL"),
    reason="需要真实 PostgreSQL；设置 MIGRATION_TEST_POSTGRES_URL 后启用",
)
def test_postgres_round_trip(monkeypatch):
    """§6.1：SQLite 绿灯不代表 PostgreSQL 绿灯。

    差异点：SQLite 默认不强制外键，且 ALTER TABLE 能力弱、Alembic 会走 batch 模式
    重建表——那根本不是生产上执行的同一条代码路径。
    """
    url = os.environ["MIGRATION_TEST_POSTGRES_URL"]
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    config = alembic_config()
    try:
        command.upgrade(config, CLASS_REVISION)
        assert set(CLASS_TABLES) <= table_names(url)
        command.downgrade(config, PREVIOUS_HEAD)
        assert not (set(CLASS_TABLES) & table_names(url))
        command.upgrade(config, CLASS_REVISION)
    finally:
        get_settings.cache_clear()
