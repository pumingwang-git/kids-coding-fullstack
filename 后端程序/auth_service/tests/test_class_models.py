from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.class_groups import active_class_teacher_assignments, active_students_for_class
from app.models import Base, ClassGroup, ClassMember, ClassTeacher, User


def test_class_read_queries_only_return_current_relationships(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'class-models.db'}")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            db.add_all(
                [
                    User(
                        id=1,
                        username="student-1",
                        email="student-1@example.com",
                        hashed_password="hash-1",
                    ),
                    User(
                        id=2,
                        username="student-2",
                        email="student-2@example.com",
                        hashed_password="hash-2",
                    ),
                    ClassGroup(id=1, name="A 班", course_id=1),
                    ClassMember(class_id=1, student_id=1),
                    ClassMember(
                        class_id=1,
                        student_id=2,
                        status="left",
                        joined_at=datetime(2026, 8, 1, tzinfo=UTC),
                        left_at=datetime(2026, 8, 2, tzinfo=UTC),
                    ),
                    ClassTeacher(
                        class_id=1,
                        admin_user_id=7,
                        role_in_class="teacher",
                    ),
                    ClassTeacher(
                        class_id=2,
                        admin_user_id=7,
                        role_in_class="assistant",
                        assigned_at=datetime(2026, 8, 1, tzinfo=UTC),
                        ended_at=datetime(2026, 8, 2, tzinfo=UTC),
                    ),
                ]
            )
            db.commit()

            assert [student.id for student in active_students_for_class(db, 1)] == [1]
            assignments = active_class_teacher_assignments(db, 7)
            assert [(row.class_id, row.role_in_class) for row in assignments] == [(1, "teacher")]
    finally:
        engine.dispose()
