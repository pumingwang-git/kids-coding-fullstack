from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import create_admin
from app.models import Base
from app.permissions import (
    ACADEMIC_ADMIN_ROLE,
    ASSISTANT_ROLE,
    GLOBAL_SCOPE,
    KNOWN_ROLE_NAMES,
    KNOWN_ROLES,
    ROLE_SCOPE_NOTES,
    ROLE_SCOPES,
    SCOPE_LABELS,
    TEACHER_ROLE,
    is_editor,
    is_reviewer,
    is_super,
    validate_admin_role,
    visible_class_ids,
)


def admin(role: str):
    return SimpleNamespace(id=1, role=role)


def test_known_roles_include_e1_roles_and_legacy_admin():
    assert KNOWN_ROLES == {
        "super_admin",
        "editor",
        "admin",
        "reviewer",
        TEACHER_ROLE,
        ASSISTANT_ROLE,
        ACADEMIC_ADMIN_ROLE,
    }
    assert tuple(KNOWN_ROLE_NAMES) == (
        "super_admin",
        "editor",
        "admin",
        "reviewer",
        "teacher",
        "assistant",
        "academic_admin",
    )


@pytest.mark.parametrize("role", KNOWN_ROLE_NAMES)
def test_validate_admin_role_accepts_every_known_role(role):
    assert validate_admin_role(role) == role


def test_validate_admin_role_lists_legal_values_for_invalid_role():
    with pytest.raises(ValueError) as exc_info:
        validate_admin_role("techer")

    assert str(exc_info.value) == (
        "非法管理员角色 'techer'；合法取值："
        "super_admin、editor、admin、reviewer、teacher、assistant、academic_admin。"
    )


@pytest.mark.parametrize("role", [TEACHER_ROLE, ASSISTANT_ROLE, ACADEMIC_ADMIN_ROLE])
def test_new_roles_do_not_gain_existing_content_or_review_permissions(role):
    assert not is_super(admin(role))
    assert not is_editor(admin(role))
    assert not is_reviewer(admin(role))


@pytest.mark.parametrize("role", KNOWN_ROLE_NAMES)
def test_every_role_declares_a_scope_and_a_note(role):
    assert ROLE_SCOPES[role] in SCOPE_LABELS
    assert ROLE_SCOPE_NOTES[role].strip()


@pytest.mark.parametrize("role", KNOWN_ROLE_NAMES)
def test_declared_scope_matches_visible_class_ids(role):
    """展示用的 scope 不能与真正生效的范围函数分叉。

    全局角色必须返回 `None`（不受限），其余角色必须返回集合；受限角色
    在空库上的真实查询也必须成功，不能靠缺失 db 参数的静默逃生口通过。
    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    try:
        with session_factory() as db:
            actual = visible_class_ids(admin(role), db)
    finally:
        engine.dispose()

    if ROLE_SCOPES[role] == GLOBAL_SCOPE:
        assert actual is None
    else:
        assert actual == set()


def test_create_admin_rejects_invalid_role_before_database_access(monkeypatch, capsys):
    monkeypatch.setenv("ADMIN_USERNAME", "teacher-1")
    monkeypatch.setenv("ADMIN_PASSWORD", "Admin-pass-123!")
    monkeypatch.setenv("ADMIN_ROLE", "techer")
    monkeypatch.setattr(create_admin, "get_settings", lambda: pytest.fail("不应读取数据库配置"))
    monkeypatch.setattr(
        create_admin,
        "build_database",
        lambda _url: pytest.fail("非法角色不应连接数据库"),
    )

    with pytest.raises(SystemExit) as exc_info:
        create_admin.main()

    assert exc_info.value.code == 1
    assert "非法管理员角色 'techer'" in capsys.readouterr().err
