"""Cron entry point for idempotent in-app homework due reminders.

Run every hour from the system scheduler.  This deliberately has no Celery
dependency: notification delivery is an ordinary database transaction.
"""
from __future__ import annotations

import argparse
from datetime import timedelta

from sqlalchemy import select

from .config import get_settings
from .course_access import enrollment_predicates
from .database import build_database
from .models import (
    Course,
    CourseLesson,
    CourseLessonBlock,
    Enrollment,
    ExamLink,
    LessonBlockCompletion,
    AttemptAnswer,
    LessonPaperBlock,
    Notification,
    NotificationReceipt,
    Paper,
    PaperAttempt,
)
from .notification_service import create_notification, ensure_notification_recipients
from .security import as_utc, utcnow
from .student_tasks import DUE_SOON_HOURS
from .notification_links import lesson_homework_link, exam_attempt_link


def send_due_reminders(db, *, now=None, dry_run: bool = False) -> int:
    now = now or utcnow()
    sent = 0
    rows = db.execute(
        select(LessonPaperBlock, CourseLessonBlock, CourseLesson, Enrollment.student_id)
        .join(CourseLessonBlock, CourseLessonBlock.id == LessonPaperBlock.block_id)
        .join(CourseLesson, CourseLesson.id == CourseLessonBlock.lesson_id)
        .join(Enrollment, Enrollment.course_id == CourseLesson.course_id)
        .where(LessonPaperBlock.mode == "homework", LessonPaperBlock.due_at.is_not(None),
               *enrollment_predicates(now))
    ).all()
    for detail, block, lesson, student_id in rows:
        due = as_utc(detail.due_at)
        if due is None or due <= now or due > now + timedelta(hours=DUE_SOON_HOURS):
            continue
        completed = db.scalar(select(LessonBlockCompletion.id).where(
            LessonBlockCompletion.user_id == student_id,
            LessonBlockCompletion.block_id == block.id,
        ))
        if completed:
            continue
        due_key = due.isoformat()
        idem = f"homework-due:{block.id}:{student_id}:{due_key}:hours{DUE_SOON_HOURS}"
        exists = db.scalar(select(Notification.id).where(Notification.idempotency_key == idem))
        if exists:
            continue
        sent += 1
        if dry_run:
            continue
        create_notification(
            db, kind="homework_due_soon", title="作业即将截止",
            body=f"《{block.title}》将在 {due_key} 截止，请及时完成。",
            target_type="lesson_homework", target_id=block.id,
            source_type="lesson_homework", source_id=block.id,
            link_url=lesson_homework_link(lesson.id, block.id),
            idempotency_key=idem,
            recipients=[{"user_id": student_id, "admin_user_id": None}],
        )
    if not dry_run:
        db.commit()
    return sent


def backfill_published_course_receipts(db, *, now=None, dry_run: bool = False) -> int:
    """Attach a publish receipt when a previously future enrollment becomes active."""

    now = now or utcnow()
    courses = db.scalars(select(Course).where(Course.status == "published")).all()
    added = 0
    for course in courses:
        notification = db.scalar(select(Notification).where(
            Notification.idempotency_key == f"course-published:{course.id}:{course.publish_generation}",
            Notification.revoked_at.is_(None),
        ))
        if notification is None:
            continue
        recipients = list(db.scalars(select(Enrollment.student_id).where(
            Enrollment.course_id == course.id,
            *enrollment_predicates(now),
        ).distinct()))
        if dry_run:
            for student_id in recipients:
                exists = db.scalar(select(NotificationReceipt.id).where(
                    NotificationReceipt.notification_id == notification.id,
                    NotificationReceipt.user_id == student_id,
                ))
                added += int(exists is None)
            continue
        added += ensure_notification_recipients(
            db, notification,
            [{"user_id": student_id, "admin_user_id": None} for student_id in recipients],
        )
    if not dry_run:
        db.commit()
    return added


def maybe_publish_result_notification(db, *, attempt: PaperAttempt, paper_title: str,
                                      source) -> bool:
    """Create the personal result notification for an already sealed attempt.

    This deliberately accepts only the facts produced by the exam workflow.
    In particular, a caller cannot supply a score or recipient independent of
    the sealed attempt.
    """

    if source.show_score != "immediate" or attempt.status != "submitted" or attempt.submitted_at is None:
        return False
    lesson_block = db.get(CourseLessonBlock, attempt.source_id)
    if lesson_block is not None and lesson_block.block_type == "homework":
        kind = "homework_graded"
        link = lesson_homework_link(lesson_block.lesson_id, lesson_block.id)
    else:
        kind = "exam_result_published"
        link = exam_attempt_link(db.get(ExamLink, attempt.source_id).access_token)
    create_notification(
        db, kind=kind, title="作业成绩已发布" if lesson_block is not None else "考试成绩已发布",
        body=f"《{paper_title}》已完成判分，成绩为 {attempt.total_score} 分。",
        target_type="paper_attempt", target_id=attempt.id,
        source_type=source.source_type, source_id=attempt.source_id,
        link_url=link,
        idempotency_key=f"exam-result:{attempt.id}",
        recipients=[{"user_id": attempt.user_id, "admin_user_id": None}],
    )
    return True


send_exam_result_notification = maybe_publish_result_notification


def send_after_close_exam_result_notifications(db, *, now=None,
                                                dry_run: bool = False) -> int:
    """Notify sealed exam attempts once an ``after_close`` score becomes public."""

    now = now or utcnow()
    rows = db.execute(
        select(PaperAttempt, ExamLink, Paper.title)
        .join(ExamLink, ExamLink.id == PaperAttempt.source_id)
        .join(Paper, Paper.id == PaperAttempt.paper_id)
        .where(
            PaperAttempt.source_type == "exam_link",
            PaperAttempt.status == "submitted",
            ExamLink.show_score == "after_close",
            ExamLink.close_at.is_not(None),
            ExamLink.close_at <= now,
        )
    ).all()
    sent = 0
    for attempt, link, paper_title in rows:
        from .attempt_source import from_exam_link
        from .routers.exam import _score_visible
        source = from_exam_link(link)
        if not _score_visible(source, now):
            continue
        pending = db.scalar(select(AttemptAnswer.id).where(
            AttemptAnswer.attempt_id == attempt.id,
            AttemptAnswer.judge_status.in_(["pending", "queued", "judging"]),
        ))
        if pending is not None:
            continue
        idem = f"exam-result:{attempt.id}"
        if db.scalar(select(Notification.id).where(Notification.idempotency_key == idem)):
            continue
        sent += 1
        if dry_run:
            continue
        create_notification(
            db, kind="exam_result_published", title="考试成绩已发布",
            body=f"《{paper_title}》已完成判分，成绩为 {attempt.total_score} 分。",
            target_type="paper_attempt", target_id=attempt.id,
            source_type="exam_link", source_id=link.id,
            link_url=exam_attempt_link(link.access_token),
            idempotency_key=idem,
            recipients=[{"user_id": attempt.user_id, "admin_user_id": None}],
        )
    if not dry_run:
        db.commit()
    return sent


def main() -> None:
    parser = argparse.ArgumentParser(description="发送即将截止的作业站内提醒。")
    parser.add_argument("--dry-run", action="store_true", help="只统计，不写入通知")
    args = parser.parse_args()
    settings = get_settings()
    engine, factory = build_database(settings.database_url)
    db = factory()
    try:
        count = send_due_reminders(db, dry_run=args.dry_run)
        count += backfill_published_course_receipts(db, dry_run=args.dry_run)
        count += send_after_close_exam_result_notifications(db, dry_run=args.dry_run)
    finally:
        db.close()
        engine.dispose()
    print(f"{'将发送' if args.dry_run else '已发送'} {count} 条通知。")


if __name__ == "__main__":
    main()
