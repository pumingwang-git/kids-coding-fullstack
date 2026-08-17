from types import SimpleNamespace

from sqlalchemy import select

from app.models import User
from app.permissions import visible_class_ids, visible_student_ids


def _admin(role: str):
    return SimpleNamespace(role=role)


def _student_query(ids: set[int] | None):
    stmt = select(User.id)
    if ids is not None:
        stmt = stmt.where(User.id.in_(ids))
    return stmt


def test_unrestricted_none_and_restricted_empty_set_build_different_queries():
    """None 是不受限；空集是受限且无可见学生，不能用 ``if not ids`` 合并。"""
    unrestricted = visible_student_ids(_admin("super_admin"), None)
    restricted = visible_student_ids(_admin("teacher"), None)

    assert unrestricted is None
    assert restricted == set()
    assert "WHERE" not in str(_student_query(unrestricted))
    assert "WHERE" in str(_student_query(restricted))


def test_e1_class_scope_roles():
    assert visible_class_ids(_admin("super_admin"), None) is None
    assert visible_class_ids(_admin("academic_admin"), None) is None
    assert visible_class_ids(_admin("teacher"), None) == set()
    assert visible_class_ids(_admin("assistant"), None) == set()


def test_content_roles_do_not_gain_global_student_scope():
    for role in ("editor", "admin", "reviewer"):
        assert visible_student_ids(_admin(role), None) == set()
