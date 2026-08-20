from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.homework_roster import build_homework_roster
from app.lesson_homework_kinds import PAPER_KIND, SCRATCH_KIND
from app.models import (
    Base, ClassGroup, ClassMember, Course, CourseLesson, CourseLessonBlock,
    CourseSection, Enrollment, LearningArea, LessonPaperBlock, LessonScratchBlock,
    Paper, PaperAttempt, ScratchChallenge, ScratchProject, ScratchProjectRevision,
    ScratchSubmission, User,
)


NOW = datetime(2026, 8, 20, tzinfo=UTC)


@pytest.fixture
def db(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'homework-roster.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def _seed_roster(db: Session, kind):
    area = LearningArea(key=f"homework-{kind.key}", name="作业", status="active")
    course = Course(title="作业课", area_key=area.key, status="published")
    paper = Paper(title="作业卷", status="published")
    blocked = User(username=f"{kind.key}-blocked", email=f"{kind.key}-blocked@example.com",
                   hashed_password="hash")
    submitted = User(username=f"{kind.key}-submitted", email=f"{kind.key}-submitted@example.com",
                     hashed_password="hash")
    outsider = User(username=f"{kind.key}-outsider", email=f"{kind.key}-outsider@example.com",
                   hashed_password="hash")
    db.add_all([area, course, paper, blocked, submitted, outsider])
    db.flush()
    section = CourseSection(course_id=course.id, title="第一章")
    db.add(section)
    db.flush()
    lesson = CourseLesson(course_id=course.id, section_id=section.id, title="作业课时")
    group = ClassGroup(name="作业班", course_id=course.id, status="active")
    db.add_all([lesson, group])
    db.flush()
    block = CourseLessonBlock(lesson_id=lesson.id, block_type=kind.block_type,
                              title=f"{kind.label}块", sort_order=0)
    db.add(block)
    db.flush()
    db.add_all([
        ClassMember(class_id=group.id, student_id=blocked.id),
        ClassMember(class_id=group.id, student_id=submitted.id),
        Enrollment(student_id=blocked.id, course_id=course.id, status="active",
                   opened_at=NOW - timedelta(days=2), expires_at=NOW - timedelta(days=1)),
        Enrollment(student_id=submitted.id, course_id=course.id, status="active",
                   opened_at=NOW - timedelta(days=1)),
    ])
    if kind is PAPER_KIND:
        db.add(LessonPaperBlock(block_id=block.id, paper_id=paper.id, mode="homework",
                                attempt_limit=2, due_at=None))
        db.flush()
        db.add(PaperAttempt(source_type=kind.student_source_type, source_id=block.id,
                            paper_id=paper.id, user_id=submitted.id, attempt_no=1,
                            status="submitted", submitted_at=NOW))
    else:
        challenge = ScratchChallenge(title="作业挑战", status="published")
        db.add(challenge)
        db.flush()
        db.add(LessonScratchBlock(block_id=block.id, challenge_id=challenge.id))
        project = ScratchProject(student_id=submitted.id, challenge_id=challenge.id,
                                 lesson_block_id=block.id, current_revision_no=1,
                                 revision_count=1)
        db.add(project)
        db.flush()
        revision = ScratchProjectRevision(project_id=project.id, revision_no=1,
                                          sb3_key="test.sb3", sha256="0" * 64)
        db.add(revision)
        db.flush()
        db.add(ScratchSubmission(user_id=submitted.id, lesson_block_id=block.id,
                                 lesson_id=lesson.id, project_id=project.id,
                                 project_revision_id=revision.id, challenge_id=challenge.id,
                                 status="passed", passed=True, score=100,
                                 submitted_at=NOW))
    db.commit()
    return group, block, blocked, submitted


@pytest.mark.parametrize("kind", [PAPER_KIND, SCRATCH_KIND], ids=["paper", "scratch"])
def test_homework_roster_uses_real_class_facts_for_each_kind(db, kind):
    group, block, blocked, submitted = _seed_roster(db, kind)

    result = build_homework_roster(db, group.id, kind, block.id, now=NOW)

    assert result["roster_people"] == 2
    assert result["submitted_people"] == 1
    assert result["not_submitted_people"] == 1
    assert result["submitted_attempts"] == 1
    assert [row["student"]["id"] for row in result["not_submitted"]] == [blocked.id]
    assert result["not_submitted"][0]["access_blocked"] is True
    assert submitted.id not in {row["student"]["id"] for row in result["not_submitted"]}


def test_homework_roster_returns_zero_not_null_when_everyone_submits(db):
    group, block, blocked, _submitted = _seed_roster(db, PAPER_KIND)
    paper_id = db.scalar(sa.select(LessonPaperBlock.paper_id).where(
        LessonPaperBlock.block_id == block.id
    ))
    db.add(PaperAttempt(source_type=PAPER_KIND.student_source_type, source_id=block.id,
                        paper_id=paper_id, user_id=blocked.id, attempt_no=1,
                        status="submitted", submitted_at=NOW))
    db.commit()

    result = build_homework_roster(db, group.id, PAPER_KIND, block.id, now=NOW)

    assert result["roster_people"] == 2
    assert result["not_submitted_people"] == 0
    assert result["not_submitted"] == []
