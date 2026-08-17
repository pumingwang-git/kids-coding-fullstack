from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect
from sqlalchemy.exc import OperationalError
from starlette.datastructures import MutableHeaders
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from .config import Settings, get_settings
from .database import build_database
from .judge import build_judge_client
from .judge.runner import JudgeRunner
from .learning_catalog import ensure_learning_catalog
from .mailer import InMemoryEmailSender, SmtpEmailSender
from .models import Base
from .rate_limit import InMemoryRateLimiter, RedisRateLimiter
from .routers.admin_auth import router as admin_router
from .routers.admin_classes import router as admin_classes_router
from .routers.admin_course_content import router as admin_course_content_router
from .routers.admin_courses import router as admin_courses_router
from .routers.admin_dryrun import router as admin_dryrun_router
from .routers.admin_dryrun import run_dry_run
from .routers.admin_material_imports import (
    router as admin_material_imports_router,
)
from .routers.admin_material_imports import (
    sweep_material_imports,
)
from .routers.admin_materials import router as admin_materials_router
from .routers.admin_materials import sweep_material_uploads
from .routers.admin_media import router as admin_media_router
from .routers.admin_papers import router as admin_papers_router
from .routers.admin_questions import router as admin_questions_router
from .routers.admin_results import router as admin_results_router
from .routers.admin_scratch import router as admin_scratch_router
from .routers.admin_videos import router as admin_videos_router
from .routers.auth_secure import router
from .routers.courses import router as student_courses_router
from .routers.exam import judge_submission, sweep_stale_judgings
from .routers.exam import router as exam_router
from .routers.focus import router as focus_router
from .routers.learning_catalog import admin_router as admin_learning_catalog_router
from .routers.learning_catalog import router as learning_catalog_router
from .routers.lesson_practice import router as lesson_practice_router
from .routers.lesson_practice import run_lesson_code
from .routers.math_games import router as math_games_router
from .routers.scratch import router as scratch_router
from .routers.scratch_works import router as scratch_works_router
from .routers.student_mistakes import router as student_mistakes_router
from .routers.student_profile import router as student_profile_router
from .routers.typing import router as typing_router
from .routers.video_play import play_router as video_play_stream_router
from .routers.video_play import router as video_play_router


class NoStoreJSONMiddleware:
    """私有 JSON 接口统一禁止共享缓存（P0-2）。

    /me、课时详情、题目、进度、播放令牌等响应带用户身份/解锁状态/学习进度，
    必须显式 Cache-Control: private, no-store——不能依赖浏览器对 JSON 的默认行为，
    也不能被生产 Nginx/CDN 误缓存（权限与数据隔离问题，不只是性能）。

    用**纯 ASGI 中间件**而不是 BaseHTTPMiddleware：后者会缓冲响应体，视频流/资料流
    的 StreamingResponse 会被整段读进内存、Range 分片失效。这里只在
    http.response.start 消息上改头，不碰 body，流式转发零影响。

    只对 application/json 生效：资料/视频二进制流各自代理已带
    private, max-age（video_play.stream / _proxy_material_stream），不受影响。
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                if "application/json" in headers.get("content-type", ""):
                    headers["Cache-Control"] = "private, no-store"
            await send(message)

        await self.app(scope, receive, send_wrapper)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    settings.validate_production()
    engine, session_factory = build_database(settings.database_url)
    # 迁移负责建表，初始化器只补齐缺失目录。测试环境由 create_all 建表；尚未迁移的
    # 开发库跳过初始化，避免应用导入阶段用业务代码替代 Alembic。
    if inspect(engine).has_table("learning_areas"):
        ensure_learning_catalog(session_factory)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if settings.environment == "test":
            Base.metadata.create_all(engine)
        # 上一次进程退出时丢在半路的判题，在这里收尾——否则学员端会对着
        # 一条永远转圈的 queued 记录发呆。
        sweep_stale_judgings(session_factory, settings.judge_stale_seconds)
        # 资料模块同理：complete 后未跑完的 sha256 校验、迁移 finalize 中途退出，
        # 都会把记录卡在 uploading / finalizing。启动时扫尾恢复（任务本身幂等，
        # 重复执行无害；workers 进程与 API 进程走同一 create_app，也会扫到）。
        sweep_material_uploads(settings, session_factory)
        sweep_material_imports(settings, session_factory)
        try:
            yield
        finally:
            app.state.judge_runner.shutdown()
            engine.dispose()

    app = FastAPI(title="学习系统认证 API", lifespan=lifespan)

    @app.exception_handler(OperationalError)
    async def database_busy_handler(_request, _exc):
        return JSONResponse(status_code=503, content={"detail": "请求正在并发处理，请稍后重试。"})

    app.state.settings = settings
    app.state.session_factory = session_factory
    app.state.rate_limiter = (
        RedisRateLimiter(settings.redis_url) if settings.redis_url else InMemoryRateLimiter()
    )
    app.state.mailer = SmtpEmailSender(settings) if settings.smtp_host else InMemoryEmailSender()
    app.state.judge = build_judge_client(settings)
    # 判题跑在这个池子里，不占请求线程、不占请求那条 DB 连接。
    # 池子大小 ≈ 2× go-judge 的 -parallelism，见 config.judge_workers。
    def dispatch_judge_task(task):
        """一个池子跑两种任务：学员的代码提交，和管理端的参考代码试跑。

        **不给试跑单开一个池子**：池子大小是全局判题并发闸（≈ 2× go-judge 的
        -parallelism），开第二个就等于把闸门变成两倍，两边加起来能把沙箱压垮。
        试跑与考试的冲突在入口处解决——有 ongoing attempt 时直接拒绝试跑。
        """
        if task.kind == "dry_run":
            run_dry_run(session_factory, app.state.judge, task, settings)
        elif task.kind == "lesson_run":
            run_lesson_code(session_factory, app.state.judge, task, settings)
        else:
            judge_submission(session_factory, app.state.judge, task, settings)

    app.state.judge_runner = JudgeRunner(
        dispatch_judge_task,
        workers=settings.judge_workers,
        queue_max=settings.judge_queue_max,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", "X-CSRF-Token"],
    )
    if settings.environment == "production":
        app.add_middleware(HTTPSRedirectMiddleware)
    app.add_middleware(NoStoreJSONMiddleware)
    if settings.trusted_proxies:
        app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=settings.trusted_proxies)
    app.include_router(admin_router)
    app.include_router(admin_classes_router)
    app.include_router(admin_courses_router)
    app.include_router(admin_learning_catalog_router)
    app.include_router(admin_course_content_router)
    app.include_router(admin_dryrun_router)
    app.include_router(admin_media_router)
    app.include_router(admin_materials_router)
    app.include_router(admin_material_imports_router)
    app.include_router(admin_videos_router)
    app.include_router(admin_questions_router)
    app.include_router(admin_papers_router)
    app.include_router(admin_results_router)
    app.include_router(admin_scratch_router)
    app.include_router(exam_router)
    app.include_router(router)
    app.include_router(student_courses_router)
    app.include_router(learning_catalog_router)
    app.include_router(lesson_practice_router)
    app.include_router(scratch_router)
    app.include_router(scratch_works_router)
    app.include_router(focus_router)
    app.include_router(student_mistakes_router)
    app.include_router(student_profile_router)
    app.include_router(typing_router)
    app.include_router(math_games_router)
    app.include_router(video_play_router)
    app.include_router(video_play_stream_router)
    # 题干配图的静态服务：**只在非生产挂**。生产由 nginx 直发——让 uvicorn 发静态文件
    # 是白占 worker，而图片的请求量随题量线性涨。
    # 挂载点必须是 /media，与 admin_media.media_relative_path() 拼出的 URL 一致。
    # test 也不挂：每建一次测试 app 就 mkdir 一个目录，会在仓库里堆出空壳。
    # 用例要验的是"文件落到磁盘上了"，直接断言路径存在即可，不需要真的 HTTP 取一次。
    if settings.environment not in ("production", "test"):
        media_root = Path(settings.media_upload_root)
        media_root.mkdir(parents=True, exist_ok=True)
        app.mount("/media", StaticFiles(directory=media_root), name="media")
        # 课包封面：独立存储区域（与题干配图分开），挂载点 /course-covers 与
        # admin_media.course_cover_relative_path() 拼出的 URL 一致。生产同样由 nginx 直发。
        cover_root = Path(settings.course_cover_upload_root)
        cover_root.mkdir(parents=True, exist_ok=True)
        app.mount("/course-covers", StaticFiles(directory=cover_root), name="course-covers")
        # 学生头像：独立存储区域（config.avatar_upload_root 注释了为什么不能进 data/media）。
        # 挂载点 /avatars 与 student_profile._avatar_relative_path() 拼出的 URL 一致。
        avatar_root = Path(settings.avatar_upload_root)
        avatar_root.mkdir(parents=True, exist_ok=True)
        app.mount("/avatars", StaticFiles(directory=avatar_root), name="avatars")
    return app


app = create_app()
