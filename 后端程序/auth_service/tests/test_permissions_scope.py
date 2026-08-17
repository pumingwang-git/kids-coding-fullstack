from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Base, ClassMember, ClassTeacher, User
from app.permissions import visible_class_ids, visible_student_ids


def _admin(role: str):
    return SimpleNamespace(id=5, role=role)


def _student_query(ids: set[int] | None):
    stmt = select(User.id)
    if ids is not None:
        stmt = stmt.where(User.id.in_(ids))
    return stmt


def test_unrestricted_none_and_restricted_empty_set_build_different_queries():
    """None 是不受限；空集是受限且无可见学生，不能用 ``if not ids`` 合并。"""
    unrestricted = visible_student_ids(_admin("super_admin"), None)

    assert unrestricted is None
    with pytest.raises(TypeError, match="数据库会话"):
        visible_student_ids(_admin("teacher"), None)
    assert "WHERE" not in str(_student_query(unrestricted))
    assert "WHERE" in str(_student_query(set()))


def test_class_scope_roles_require_a_database_session():
    assert visible_class_ids(_admin("super_admin"), None) is None
    assert visible_class_ids(_admin("academic_admin"), None) is None
    with pytest.raises(TypeError, match="数据库会话"):
        visible_class_ids(_admin("teacher"), None)
    with pytest.raises(TypeError, match="数据库会话"):
        visible_class_ids(_admin("assistant"), None)


def test_content_roles_do_not_gain_global_student_scope():
    for role in ("editor", "admin", "reviewer"):
        assert visible_student_ids(_admin(role), None) == set()


def test_class_scope_uses_current_teacher_assignments_and_members(tmp_path):
    from datetime import UTC, datetime

    import sqlalchemy as sa

    engine = sa.create_engine(f"sqlite:///{tmp_path / 'scope.db'}")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            db.add_all(
                [
                    User(id=1, username="s1", email="s1@example.com", hashed_password="hash"),
                    User(id=2, username="s2", email="s2@example.com", hashed_password="hash"),
                    User(id=3, username="s3", email="s3@example.com", hashed_password="hash"),
                    ClassTeacher(class_id=10, admin_user_id=5, role_in_class="teacher"),
                    ClassTeacher(
                        class_id=20,
                        admin_user_id=5,
                        role_in_class="assistant",
                        assigned_at=datetime(2026, 8, 1, tzinfo=UTC),
                        ended_at=datetime(2026, 8, 2, tzinfo=UTC),
                    ),
                    ClassTeacher(class_id=30, admin_user_id=6, role_in_class="teacher"),
                    ClassMember(class_id=10, student_id=1),
                    ClassMember(
                        class_id=10,
                        student_id=2,
                        status="left",
                        joined_at=datetime(2026, 8, 1, tzinfo=UTC),
                        left_at=datetime(2026, 8, 2, tzinfo=UTC),
                    ),
                    ClassMember(class_id=20, student_id=3),
                ]
            )
            db.commit()

            assert visible_class_ids(_admin("teacher"), db) == {10}
            assert visible_student_ids(_admin("teacher"), db) == {1}
    finally:
        engine.dispose()
