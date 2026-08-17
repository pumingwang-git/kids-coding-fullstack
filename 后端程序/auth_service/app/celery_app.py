"""Celery 应用：视频转码等异步任务。

本地开发（无 REDIS_URL）用 eager 模式——任务同步执行，不依赖 broker；
生产配置 redis_url 后由 `celery -A app.celery_app worker` 异步消费。

启动 worker（生产/服务器）：
    celery -A app.celery_app worker -l info -Q transcode
"""
from __future__ import annotations



from celery import Celery

from .config import get_settings


def make_celery() -> Celery:
    settings = get_settings()
    app = Celery(
        "auth_service",
        include=["app.tasks.transcode"],
    )
    app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="Asia/Shanghai",
        enable_utc=True,
        task_track_started=True,
        # 队列：转码单独一个，便于按优先级/机器隔离
        task_routes={"app.tasks.transcode.*": {"queue": "transcode"}},
    )
    if settings.redis_url:
        app.conf.broker_url = settings.redis_url
        app.conf.result_backend = settings.redis_url
        app.conf.task_always_eager = False
    else:
        # 本地无 Redis：eager 同步执行。broker 用纯 Python 的 memory transport 兜底
        # （不会被实际使用；filesystem:// 在 Windows 上 import 时要 pywintypes，故不用）。
        app.conf.broker_url = "memory://"
        app.conf.result_backend = "cache+memory://"
        app.conf.task_always_eager = True
        app.conf.task_eager_propagates = True
    return app


celery_app = make_celery()
