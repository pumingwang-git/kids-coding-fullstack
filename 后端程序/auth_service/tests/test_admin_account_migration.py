"""后台账号生命周期迁移必须按目标 revision 独立验证。"""

from pathlib import Path

import pytest
import sqlalchemy as sa

from alembic import command
from alembic.config import Config
from app.config import get_settings

ROOT = Path(__file__).resolve().parents[1]


def test_0071_adds_password_change_flag_from_0070(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'admin-account-0071.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    engine = sa.create_engine(url)
    try:
        command.upgrade(config, "0070_export_jobs")
        assert "must_change_password" not in {
            column["name"] for column in sa.inspect(engine).get_columns("admin_users")
        }
        with engine.begin() as connection:
            connection.execute(sa.text(
                "INSERT INTO admin_users "
                "(username, password_hash, display_name, role, status, failed_login_count) "
                "VALUES ('existing-admin', 'hash', 'Existing', 'editor', 'active', 0)"
            ))

        command.upgrade(config, "0071_admin_account_lifecycle")
        columns = {
            column["name"]: column
            for column in sa.inspect(engine).get_columns("admin_users")
        }
        assert columns["must_change_password"]["nullable"] is False
        with engine.connect() as connection:
            value = connection.scalar(sa.text(
                "SELECT must_change_password FROM admin_users WHERE username='existing-admin'"
            ))
        assert value in (False, 0)

        command.downgrade(config, "0070_export_jobs")
        assert "must_change_password" not in {
            column["name"] for column in sa.inspect(engine).get_columns("admin_users")
        }
        with engine.connect() as connection:
            assert connection.scalar(sa.text(
                "SELECT count(*) FROM admin_users WHERE username='existing-admin'"
            )) == 1
    finally:
        engine.dispose()
        get_settings.cache_clear()


def test_0072_seeds_dynamic_role_catalog_and_account_revision(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'dynamic-rbac-0072.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    engine = sa.create_engine(url)
    try:
        command.upgrade(config, "0071_admin_account_lifecycle")
        command.upgrade(config, "0072_dynamic_admin_rbac")
        inspector = sa.inspect(engine)
        assert {"admin_roles", "admin_role_capabilities"} <= set(inspector.get_table_names())
        assert "role_revision" in {
            column["name"] for column in inspector.get_columns("admin_users")
        }
        with engine.connect() as connection:
            roles = dict(connection.execute(sa.text(
                "SELECT key, is_assignable FROM admin_roles"
            )).all())
            grants = set(connection.execute(sa.text(
                "SELECT role_key, capability_key FROM admin_role_capabilities"
            )).all())
        assert roles["super_admin"] in (True, 1)
        assert roles["admin"] in (False, 0)
        assert ("teacher", "scratch_review") in grants
        assert ("super_admin", "manage_admin_roles") in grants

        command.downgrade(config, "0071_admin_account_lifecycle")
        inspector = sa.inspect(engine)
        assert "admin_roles" not in inspector.get_table_names()
        assert "role_revision" not in {
            column["name"] for column in inspector.get_columns("admin_users")
        }
    finally:
        engine.dispose()
        get_settings.cache_clear()


def test_0074_adds_and_removes_help_capability_grants(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'help-capabilities-0074.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    engine = sa.create_engine(url)
    try:
        command.upgrade(config, "0073_scratch_work_cover")
        command.upgrade(config, "0074_help_chat_realtime")
        with engine.connect() as connection:
            grants = set(connection.execute(sa.text(
                "SELECT role_key, capability_key FROM admin_role_capabilities "
                "WHERE capability_key LIKE 'help_%' "
                "OR capability_key LIKE 'realtime_%' "
                "OR capability_key LIKE 'support_content_%'"
            )).all())
        assert grants == {
            ("teacher", "help_respond"),
            ("teacher", "realtime_assist"),
            ("assistant", "help_respond"),
            ("assistant", "realtime_assist"),
            ("academic_admin", "support_content_request"),
            ("super_admin", "support_content_request"),
            ("super_admin", "support_content_approve"),
        }

        command.downgrade(config, "0073_scratch_work_cover")
        with engine.connect() as connection:
            remaining = connection.scalar(sa.text(
                "SELECT count(*) FROM admin_role_capabilities "
                "WHERE capability_key LIKE 'help_%' "
                "OR capability_key LIKE 'realtime_%' "
                "OR capability_key LIKE 'support_content_%'"
            ))
        assert remaining == 0
    finally:
        engine.dispose()
        get_settings.cache_clear()


def test_0081_grants_super_admin_help_response(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'super-help-capability-0081.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    engine = sa.create_engine(url)
    try:
        command.upgrade(config, "0080_restore_help_assign_rev")
        with engine.connect() as connection:
            assert connection.scalar(sa.text(
                "SELECT count(*) FROM admin_role_capabilities "
                "WHERE role_key = 'super_admin' AND capability_key = 'help_respond'"
            )) == 0

        command.upgrade(config, "0081_grant_super_help_respond")
        with engine.connect() as connection:
            assert connection.scalar(sa.text(
                "SELECT count(*) FROM admin_role_capabilities "
                "WHERE role_key = 'super_admin' AND capability_key = 'help_respond'"
            )) == 1
    finally:
        engine.dispose()
        get_settings.cache_clear()


def test_0072_downgrade_refuses_accounts_using_custom_roles(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'dynamic-rbac-0072-refuse.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    engine = sa.create_engine(url)
    try:
        command.upgrade(config, "0072_dynamic_admin_rbac")
        with engine.begin() as connection:
            connection.execute(sa.text(
                "INSERT INTO admin_roles "
                "(key, label, description, scope, is_system, is_protected, "
                "is_assignable, revision, sort_order) "
                "VALUES ('course_operator', 'Course operator', '', 'none', 0, 0, 1, 1, 1000)"
            ))
            connection.execute(sa.text(
                "INSERT INTO admin_users "
                "(username, password_hash, display_name, role, status, failed_login_count) "
                "VALUES ('custom-role-user', 'hash', 'Custom role user', "
                "'course_operator', 'active', 0)"
            ))

        with pytest.raises(RuntimeError, match="reassign every admin account"):
            command.downgrade(config, "0071_admin_account_lifecycle")

        inspector = sa.inspect(engine)
        assert "admin_roles" in inspector.get_table_names()
        assert "role_revision" in {
            column["name"] for column in inspector.get_columns("admin_users")
        }
    finally:
        engine.dispose()
        get_settings.cache_clear()
