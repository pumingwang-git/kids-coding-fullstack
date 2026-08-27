"""管理员总览聚合接口。

该接口只负责把总览页所需的计数一次性返回；各业务对象的可见范围仍由
原有 router/permissions 口径决定，避免前端通过多次请求自行拼装指标。
"""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..metric_versions import METRIC_VERSION
from ..models import Course, Enrollment, ExamLink, Problem, Paper, User
from ..permissions import visible_student_ids
from ..course_access import enrollment_predicates
from .admin_auth import current_admin, db_session
from .admin_papers import _visible_statement as visible_papers
from .admin_questions import _visible_statement as visible_problems

router = APIRouter(prefix="/api/admin/dashboard", tags=["admin-dashboard"])


def _status_counts(db: Session, statement, statuses: tuple[str, ...]) -> dict[str, int]:
    subquery = statement.subquery()
    result = {status: 0 for status in statuses}
    for status, total in db.execute(
        select(subquery.c.status, func.count()).group_by(subquery.c.status)
    ):
        if status in result:
            result[status] = int(total)
    return result


@router.get("/overview")
def dashboard_overview(request: Request, db: Session = Depends(db_session)):
    """返回管理端总览页的单次、权限收口后的指标快照。"""
    admin = current_admin(request, db)

    course_counts = {
        "total": int(db.scalar(select(func.count()).select_from(Course)) or 0),
        "published": int(db.scalar(select(func.count()).select_from(Course).where(Course.status == "published")) or 0),
        "draft": int(db.scalar(select(func.count()).select_from(Course).where(Course.status == "draft")) or 0),
    }
    question_counts = _status_counts(db, visible_problems(admin), ("draft", "pending", "approved"))
    paper_counts = _status_counts(db, visible_papers(admin), ("draft", "published", "archived"))

    student_ids = visible_student_ids(admin, db)
    student_stmt = select(func.count()).select_from(User)
    if student_ids is not None:
        student_stmt = student_stmt.where(User.id.in_(student_ids))
    student_total = int(db.scalar(student_stmt) or 0)

    visible_paper_ids = visible_papers(admin).subquery()
    link_counts = {"active": 0, "disabled": 0}
    for status, total in db.execute(
        select(ExamLink.status, func.count())
        .join(visible_paper_ids, ExamLink.paper_id == visible_paper_ids.c.id)
        .group_by(ExamLink.status)
    ):
        if status in link_counts:
            link_counts[status] = int(total)
    link_counts["all"] = link_counts["active"] + link_counts["disabled"]

    # 这些是组织侧可解释的附加事实，时间窗必须复用课程资格唯一谓词。
    now = datetime.now(UTC)
    enrollment_stmt = select(func.count()).select_from(Enrollment).where(*enrollment_predicates(now))
    if student_ids is not None:
        enrollment_stmt = enrollment_stmt.where(Enrollment.student_id.in_(student_ids))
    active_enrollments = int(db.scalar(enrollment_stmt) or 0)

    payload = {
        "metric_version": METRIC_VERSION,
        "server_now": now,
        "courses": course_counts,
        "questions": question_counts,
        "papers": paper_counts,
        "students": {"total": student_total},
        "exam_links": link_counts,
        "course_access": {"active_enrollments": active_enrollments},
    }
    return payload
