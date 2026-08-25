"""Celery workers for large administrative exports.

The worker deliberately loads the administrator and recomputes scope at execution
time; the request-time snapshot is metadata only and is never trusted.
"""
from __future__ import annotations

from ..celery_app import celery_app
from ..config import get_settings
from ..database import build_database
from ..models import AdminUser, ExportJob
from ..permissions import exportable_class_ids, visible_class_ids
from ..routers.admin_auth import audit
from ..routers.admin_classes import build_class_relationship_csv
from ..routers.admin_teaching import build_class_insight_csv


@celery_app.task(name="app.tasks.exports.run_export_job")
def run_export_job(job_id: str):
    settings = get_settings()
    engine, SessionLocal = build_database(settings.database_url)
    db = SessionLocal()
    try:
        job = db.get(ExportJob, job_id)
        if job is None:
            return
        admin = db.get(AdminUser, job.requested_by)
        if admin is None or getattr(admin, "status", "active") != "active":
            job.status, job.error = "failed", "管理员已不可用"
            db.commit(); return
        # Explicitly recompute both scopes in the worker process.
        visible_ids = visible_class_ids(admin, db)
        export_ids = exportable_class_ids(admin, db)
        job.status = "running"; db.commit()
        if job.export_type == "class_insight":
            params = job.params or {}
            class_id = int(params["class_id"])
            if export_ids is not None and class_id not in export_ids:
                raise PermissionError("执行时管理员已无该班级导出权限")
            content, count = build_class_insight_csv(db, admin, class_id, params.get("inactive_days_gte"), export_ids)
            resource_type, resource_id = "class_insight_export", class_id
        elif job.export_type == "class_relationships":
            content, count = build_class_relationship_csv(db, admin, visible_ids)
            resource_type, resource_id = "class_relationship_export", None
        else:
            raise ValueError(f"未知导出类型: {job.export_type}")
        job.content = content.decode("utf-8")
        job.row_count = count
        job.status = "completed"
        audit(db, settings, "export_download", "success", None, admin.id,
              resource_type=resource_type, resource_id=resource_id,
              summary={"schema_version": 1, "export_type": job.export_type, "row_count": count})
        db.commit()
    except Exception as exc:
        db.rollback()
        job = db.get(ExportJob, job_id)
        if job is not None:
            job.status, job.error = "failed", str(exc)[:1000]
            db.commit()
        raise
    finally:
        db.close(); engine.dispose()
