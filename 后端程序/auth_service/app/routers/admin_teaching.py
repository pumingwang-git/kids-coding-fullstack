"""Teacher workbench routes."""
from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..class_groups import active_student_ids_by_class_for_classes, active_students_for_class
from ..class_insight import build_class_insight
from ..exam_roster import exam_participation
from ..homework_roster import build_homework_roster
from ..learning_activity import activity_rows
from ..lesson_homework_kinds import KINDS
from ..metric_versions import METRIC_VERSION
from ..models import (
    AdminUser,
    ClassGroup,
    CourseLesson,
    CourseLessonBlock,
    ExamAssignment,
    ExamLink,
    ExportJob,
    User,
)
from ..permissions import (
    CLASS_INSIGHT_EXPORT_CAPABILITY,
    can_export_class_insight_for_class,
    exportable_class_ids,
    has_capability,
    log_scope_denial,
    visible_student_ids,
)
from ..review_adapters import ScratchReviewAdapter
from ..review_queue import pending_review_count, pending_reviews
from ..security import utcnow
from ..weak_items import build_weak_items
from . import admin_classes
from .admin_auth import audit, client_ip, current_admin, db_session

router = APIRouter(prefix="/api/admin/teaching", tags=["admin-teaching"])

EXPORT_ROW_LIMIT = 5000





def _readable_class_or_404(class_id: int, request: Request, db: Session) -> ClassGroup:
    admin_classes._require_class_reader(request, db, class_id)
    class_group = db.get(ClassGroup, class_id)
    if class_group is None:
        raise HTTPException(404, "班级不存在。")
    return class_group


def _exportable_class_or_404(
    class_id: int, request: Request, db: Session
) -> tuple[AdminUser, ClassGroup, set[int] | None]:
    """Apply the export feature gate, then the stricter class scope gate."""
    admin = current_admin(request, db)
    # 保留字面量，供 capability 目录守卫确认该功能闸真实存在。
    if not has_capability(admin, "export_class_insight"):
        raise HTTPException(403, "没有导出学情 CSV 的权限。")

    class_ids = exportable_class_ids(admin, db)
    if class_ids is not None and class_id not in class_ids:
        # An assistant (and a teacher assigned only as assistant) reaches this
        # resource-specific 404 rather than revealing the class through 403.
        log_scope_denial(admin, "class_group", class_id)
        raise HTTPException(404, "班级不存在。")

    class_group = db.get(ClassGroup, class_id)
    if class_group is None:
        raise HTTPException(404, "班级不存在。")
    return admin, class_group, class_ids


def _visible_student_or_404(student_id: int, request: Request, db: Session):
    """Match the admin student directory's indistinguishable scope 404."""
    admin, class_ids = admin_classes._require_class_reader(request, db)
    student = db.get(User, student_id)
    student_ids = visible_student_ids(admin, db)
    out_of_scope = student is not None and student_ids is not None and student_id not in student_ids
    if out_of_scope:
        log_scope_denial(admin, "student", student_id)
    if student is None or out_of_scope:
        raise HTTPException(404, "学员不存在。")
    return student, class_ids


def _class_homework_items(db: Session, class_group: ClassGroup) -> list[dict]:
    """The single DTO source for the class homework endpoint and learner profile."""
    kinds_by_block_type = {kind.block_type: kind for kind in KINDS}
    blocks = db.scalars(
        select(CourseLessonBlock)
        .join(CourseLesson, CourseLesson.id == CourseLessonBlock.lesson_id)
        .where(
            CourseLesson.course_id == class_group.course_id,
            CourseLessonBlock.block_type.in_(kinds_by_block_type),
        )
        .order_by(CourseLessonBlock.id)
    ).all()
    return [
        {
            "source_type": kinds_by_block_type[block.block_type].student_source_type,
            "source_id": block.id,
            "title": block.title,
            **build_homework_roster(
                db, class_group.id, kinds_by_block_type[block.block_type], block.id
            ),
        }
        for block in blocks
    ]


def _class_exam_items(db: Session, class_id: int, class_ids: set[int] | None) -> list[dict]:
    """The single DTO source for the class exam endpoint and learner profile."""
    statement = (
        select(ExamLink)
        .join(ExamAssignment, ExamAssignment.exam_link_id == ExamLink.id)
        .where(
            ExamLink.status == "active",
            ExamAssignment.target_type == "class",
            ExamAssignment.status == "active",
        )
    )
    if class_ids is not None:
        statement = statement.where(ExamAssignment.target_id.in_(class_ids))
    links = db.scalars(statement.distinct().order_by(ExamLink.id)).all()
    return [exam_participation(db, link.id, class_id) for link in links]


@router.get("/classes")
def list_teaching_classes(
    request: Request, db: Session = Depends(db_session)
):
    _, class_ids = admin_classes._require_class_reader(request, db)
    statement = select(ClassGroup)
    if class_ids is not None:
        statement = statement.where(ClassGroup.id.in_(class_ids))
    rows = db.scalars(statement.order_by(ClassGroup.id)).all()
    insights = build_class_insight(db, {row.id for row in rows})
    return {"items": [
        admin_classes._serialize_class(row)
        | {"insight": insights[row.id]}
        for row in rows
    ]}


@router.get("/classes/{class_id}/overview")
def class_overview(
    class_id: int, request: Request, db: Session = Depends(db_session)
):
    admin, _ = admin_classes._require_class_reader(request, db, class_id)
    class_group = db.get(ClassGroup, class_id)
    if class_group is None:
        raise HTTPException(404, "班级不存在。")
    return {
        "class_id": class_id,
        "insight": build_class_insight(db, {class_id})[class_id],
        "metric_version": METRIC_VERSION,
        "capabilities": {
            CLASS_INSIGHT_EXPORT_CAPABILITY: can_export_class_insight_for_class(
                admin, db, class_id
            ),
        },
    }


def _filtered_class_students(
    db: Session, class_id: int, inactive_days_gte: int | None
) -> list[tuple[User, dict]]:
    """Shared in-roster activity query used by list and CSV export endpoints."""
    students = active_students_for_class(db, class_id)
    activity_by_student = {
        row["user_id"]: row
        for row in activity_rows(db, {student.id for student in students}, utcnow())
    }
    rows = [(student, activity_by_student[student.id]) for student in students]
    if inactive_days_gte is not None:
        rows = [
            (student, activity)
            for student, activity in rows
            if activity["inactive_days"] is not None
            and activity["inactive_days"] >= inactive_days_gte
        ]
    return rows


@router.get("/classes/{class_id}/students")
def class_students(
    class_id: int,
    request: Request,
    inactive_days_gte: int | None = Query(default=None, ge=0),
    sort: str = Query(default="last_activity_at"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(db_session),
):
    _readable_class_or_404(class_id, request, db)
    descending = sort.startswith("-")
    sort_field = sort[1:] if descending else sort
    if sort_field not in {"last_activity_at", "username"}:
        raise HTTPException(422, "不支持的排序字段。")

    student_rows = _filtered_class_students(db, class_id, inactive_days_gte)
    rows = [
        {"student": {"id": student.id, "username": student.username}, **activity}
        for student, activity in student_rows
    ]
    for row in rows:
        row.pop("user_id")
    if sort_field == "last_activity_at":
        rows.sort(
            key=lambda row: (row["last_activity_at"] is not None, row["last_activity_at"], row["student"]["username"]),
            reverse=descending,
        )
    else:
        rows.sort(key=lambda row: row["student"]["username"], reverse=descending)
    total = len(rows)
    start = (page - 1) * page_size
    return {
        "items": rows[start:start + page_size],
        "total": total,
        "metric_version": METRIC_VERSION,
    }


def build_class_insight_csv(db: Session, admin, class_id: int, inactive_days_gte: int | None = None, class_ids=None) -> tuple[bytes, int]:
    class_group = db.get(ClassGroup, class_id)
    if class_ids is None:
        class_ids = exportable_class_ids(admin, db)
    student_rows = _filtered_class_students(db, class_id, inactive_days_gte)
    students = [student for student, _ in student_rows]
    activity_by_student = {student.id: activity for student, activity in student_rows}
    student_ids = {student.id for student in students}

    homework_by_student = {student_id: {"total": 0, "submitted": 0} for student_id in student_ids}
    for item in _class_homework_items(db, class_group):
        for row in item["roster"]:
            student_id = row["student"]["id"]
            if student_id not in homework_by_student:
                continue
            homework_by_student[student_id]["total"] += 1
            if row["phase"] in {"submitted", "graded"}:
                homework_by_student[student_id]["submitted"] += 1

    exam_by_student = {student_id: {"total": 0, "participated": 0, "attempts": 0}
                       for student_id in student_ids}
    for item in _class_exam_items(db, class_id, class_ids):
        for row in item["roster"]:
            student_id = row["student"]["id"]
            if student_id not in exam_by_student:
                continue
            exam_by_student[student_id]["total"] += 1
            attempts = row["attempts"]
            exam_by_student[student_id]["attempts"] += attempts
            if attempts:
                exam_by_student[student_id]["participated"] += 1

    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow([
        "学员ID", "用户名", "最近活动", "从未学习", "未学习天数",
        "作业项数_items", "已提交作业项数_items",
        "考试项数_items", "已参与考试项数_items", "考试提交_attempts", "metric_version",
    ])
    for student in students:
        activity = activity_by_student[student.id]
        homework = homework_by_student[student.id]
        exams = exam_by_student[student.id]
        writer.writerow([
            admin_classes._csv_cell(student.id),
            admin_classes._csv_cell(student.username),
            admin_classes._csv_cell(activity["last_activity_at"]),
            admin_classes._csv_cell(activity["never_active"]),
            admin_classes._csv_cell(activity["inactive_days"]),
            homework["total"],
            homework["submitted"],
            exams["total"],
            exams["participated"],
            exams["attempts"],
            METRIC_VERSION,
        ])

    return ("\ufeff" + output.getvalue()).encode("utf-8"), len(students)


@router.get("/classes/{class_id}/export")
def export_class_insight(
    class_id: int, request: Request,
    inactive_days_gte: int | None = Query(default=None, ge=0),
    db: Session = Depends(db_session),
):
    """Export one row per currently enrolled learner; large exports become jobs."""
    admin, class_group, class_ids = _exportable_class_or_404(class_id, request, db)
    # Count before materializing CSV: <=5000 remains the synchronous sentinel.
    row_count = len(_filtered_class_students(db, class_id, inactive_days_gte))
    if row_count > EXPORT_ROW_LIMIT:
        job = ExportJob(requested_by=admin.id, export_type="class_insight",
                        params={"class_id": class_id, "inactive_days_gte": inactive_days_gte})
        db.add(job)
        db.commit()
        db.refresh(job)
        from ..tasks.exports import run_export_job
        run_export_job.delay(job.id)
        return JSONResponse(status_code=202, content={"job_id": job.id, "status": "queued"})
    content, row_count = build_class_insight_csv(db, admin, class_id, inactive_days_gte, class_ids)
    audit(db, request.app.state.settings, "export_download", "success", client_ip(request), admin.id,
          resource_type="class_insight_export", resource_id=class_id,
          summary={"schema_version": 1, "export_type": "class_insight", "row_count": row_count})
    db.commit()
    return Response(content=content, media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="class-{class_id}-insight.csv"'})


@router.get("/classes/{class_id}/homework")
def class_homework(class_id: int, request: Request, db: Session = Depends(db_session)):
    class_group = _readable_class_or_404(class_id, request, db)
    return {
        "items": _class_homework_items(db, class_group),
        "metric_version": METRIC_VERSION,
    }


@router.get("/classes/{class_id}/exams")
def class_exams(class_id: int, request: Request, db: Session = Depends(db_session)):
    _readable_class_or_404(class_id, request, db)
    _, class_ids = admin_classes._require_class_reader(request, db)
    return {
        "items": _class_exam_items(db, class_id, class_ids),
        "metric_version": METRIC_VERSION,
    }


@router.get("/review-queue")
def review_queue(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(db_session),
):
    admin, _ = admin_classes._require_class_reader(request, db)
    student_ids = visible_student_ids(admin, db)
    rows = pending_reviews(db, student_ids, page, page_size)
    adapter = ScratchReviewAdapter()
    targets = adapter.pending(db, student_ids, page, page_size)
    return {
        "items": [
            {
                "submission_id": row.id,
                "student_id": row.user_id,
                "lesson_id": row.lesson_id,
                "lesson_block_id": row.lesson_block_id,
                "challenge_id": row.challenge_id,
                "submitted_at": row.submitted_at,
                "review_endpoint": f"scratch-review.html?submission_id={row.id}",
                # Compatibility fields remain above; new clients consume the
                # source-neutral DTO and never infer one identity from another.
                "review_target": targets[index],
            }
            for index, row in enumerate(rows)
        ],
        "total": pending_review_count(db, student_ids),
        "metric_version": METRIC_VERSION,
    }


@router.get("/classes/{class_id}/weak-items")
def class_weak_items(class_id: int, request: Request, db: Session = Depends(db_session)):
    _readable_class_or_404(class_id, request, db)
    items = []
    for row in build_weak_items(db, class_id):
        rate = row.pop("score_rate")
        rate_key = "practice_correct_rate" if row["source"] == "lesson_practice" else "paper_score_rate"
        items.append({**row, rate_key: rate})
    return {"items": items, "metric_version": METRIC_VERSION}


@router.get("/students/{student_id}/profile")
def student_profile(student_id: int, request: Request, db: Session = Depends(db_session)):
    """Read-only learner profile composed only from the class workbench DTO sources."""
    student, class_ids = _visible_student_or_404(student_id, request, db)
    statement = select(ClassGroup).order_by(ClassGroup.id)
    if class_ids is not None:
        statement = statement.where(ClassGroup.id.in_(class_ids))
    candidate_groups = list(db.scalars(statement))
    student_ids_by_class = active_student_ids_by_class_for_classes(
        db, {class_group.id for class_group in candidate_groups}
    )
    class_groups = [
        class_group for class_group in candidate_groups
        if student_id in student_ids_by_class[class_group.id]
    ]

    learning = activity_rows(db, {student_id}, utcnow())[0]
    learning.pop("user_id")
    homework: list[dict] = []
    exams: list[dict] = []
    practice: list[dict] = []
    for class_group in class_groups:
        for item in _class_homework_items(db, class_group):
            row = next(row for row in item["roster"] if row["student"]["id"] == student_id)
            homework.append({
                "class_id": class_group.id,
                "source_type": item["source_type"],
                "source_id": item["source_id"],
                "title": item["title"],
                **row,
            })
        for item in _class_exam_items(db, class_group.id, class_ids):
            row = next((row for row in item["roster"] if row["student"]["id"] == student_id), None)
            if row is not None:
                exams.append({
                    "class_id": class_group.id,
                    "exam_link_id": item["exam_link_id"],
                    "name": item["name"],
                    "phase": item["phase"],
                    "phase_label": item["phase_label"],
                    **row,
                })
        practice.extend({
            "class_id": class_group.id,
            "source_type": row["source"],
            "source_id": row["source_id"],
            "source_title": row["source_title"],
            "practice_correct_rate": row["score_rate"],
        } for row in build_weak_items(db, class_group.id, student_id=student_id)
        if row["source"] == "lesson_practice")

    return {
        "student": {"id": student.id, "username": student.username},
        "learning": learning,
        "homework": homework,
        "exams": exams,
        "practice": practice,
    }
