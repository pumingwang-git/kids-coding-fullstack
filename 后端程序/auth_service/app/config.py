from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_FERNET_KEY = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="

# These values have appeared in committed example configuration. They must
# never be accepted by a production process, even if they do not use the
# development prefix.
PUBLIC_EXAMPLE_SECRETS = frozenset({
    "mNlmwhUn4C2Q-pSnZbz_6nBUcRgU-wdeL73cfXOfWMG5I3Pwfz86aITGy2XsQzmy",
    "tCjIvogPXXM6daC4K2pIGpdFj9L549zaNzEFzRnCCMLwf5NoEIZ5g_9QJzpecoP9",
    "replace-with-a-separate-random-secret",
})
SECRET_PLACEHOLDER_MARKERS = (
    "change-me",
    "replace-with",
    "development",
    "not-for-production",
    "example-secret",
)


def _is_production_secret_rejected(value: str | None) -> bool:
    if not value:
        return True
    normalized = value.strip().lower()
    return value in PUBLIC_EXAMPLE_SECRETS or any(
        marker in normalized for marker in SECRET_PLACEHOLDER_MARKERS
    )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    environment: str = "development"
    # The URL is supplied only through the environment or the local .env file.
    database_url: str
    jwt_secret_key: str = "development-only-change-me-please-32-bytes"
    jwt_previous_secret_key: str | None = None
    refresh_token_hmac_key: str = "development-refresh-token-hmac-key-change-me"
    jwt_issuer: str = "study-auth-service"
    jwt_audience: str = "study-web"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15
    refresh_token_days: int = 7  # Idle timeout, kept for existing deployments.
    refresh_absolute_days: int = 30
    # 轮换后重放宽限期：秒。多标签页/并发请求会同时携带同一个旧 refresh token
    # 调 /refresh，宽限期内视为并发刷新而非令牌被盗，不吊销会话族；设为 0 恢复严格模式。
    refresh_reuse_grace_seconds: int = Field(default=30, ge=0, le=120)
    verification_hmac_key: str = "development-verification-key-change-me"
    outbox_encryption_key: str = DEV_FERNET_KEY
    redis_url: str | None = None
    cors_origins: str = "http://localhost:5173"
    trusted_proxy_ips: str = ""
    # Optional local GeoLite2/GeoIP2 City database.  When omitted, risk
    # detection still compares privacy-preserving IP HMACs, but does not claim
    # a city that it cannot determine.
    geoip_database_path: str | None = None
    # Preferred for a China-focused deployment.  The v4/v6 xdb files are
    # queried locally and contain Chinese province/city names for China IPs.
    ip2region_v4_database_path: str | None = None
    ip2region_v6_database_path: str | None = None
    login_location_ttl_days: int = 90
    cookie_secure: bool = False
    smtp_host: str | None = None
    smtp_port: int = 465
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    login_lock_threshold: int = 5
    login_lock_base_seconds: int = 30
    login_lock_max_seconds: int = 900
    outbox_max_attempts: int = 5
    outbox_lock_seconds: int = 300
    outbox_retry_base_seconds: int = 60
    mfa_issuer: str = "Study Learning Platform"
    mfa_enabled: bool = False
    captcha_enabled: bool = True
    # HaveIBeenPwned Pwned Passwords k-anonymity breach check (server-side
    # enforcement).  Only the first five characters of the SHA-1 digest are
    # sent to the API; the suffix is matched locally.
    pwned_check_enabled: bool = True
    # False (default): an unreachable breach database logs a warning and allows
    # the request.  True: the service refuses to register/change until the
    # breach database answers, which is the fail-closed choice for production.
    pwned_check_strict: bool = False
    pwned_api_base_url: str = "https://api.pwnedpasswords.com"
    pwned_timeout_seconds: float = Field(default=3.0, gt=0, le=10)
    # Number of previous passwords kept per user; a new password may not equal
    # the current one or any of these.
    password_history_count: int = Field(default=5, ge=1, le=24)
    # B 端管理后台认证
    slider_captcha_enabled: bool = True
    admin_access_minutes: int = 30
    admin_refresh_hours: int = 12
    admin_refresh_absolute_days: int = 7
    # 轮换后重放宽限期：秒。多标签页/并发请求会同时携带同一个旧 refresh token
    # 调 /refresh，宽限期内视为并发刷新而非令牌被盗，不吊销会话族；设为 0 恢复严格模式。
    admin_refresh_reuse_grace_seconds: int = Field(default=30, ge=0, le=120)
    # OJ 测试数据：仅允许管理端上传 zip，由服务端解压到这个受控根目录。
    testdata_upload_root: str = "data/testdata"
    testdata_zip_max_bytes: int = Field(default=32 * 1024 * 1024, ge=1 * 1024 * 1024, le=256 * 1024 * 1024)
    testdata_unpacked_max_bytes: int = Field(default=128 * 1024 * 1024, ge=1 * 1024 * 1024, le=1024 * 1024 * 1024)
    testdata_max_files: int = Field(default=200, ge=2, le=2000)
    # 题干配图：内容寻址（sha256）落盘，URL 形如 /media/ab/abcd….png，由 nginx 直发。
    # ⚠️ /media 必须与后台、学员端同源——图片 URL 是站点相对路径，没有 base_url 可配。
    media_upload_root: str = "data/media"
    media_max_bytes: int = Field(default=5 * 1024 * 1024, ge=256 * 1024, le=20 * 1024 * 1024)
    # 超过就等比缩放。手机直出 4000×3000 是常态，题干里没人要看原图。
    media_max_dimension: int = Field(default=4096, ge=512, le=8192)
    # 孤儿图的宽限期：上传了但还没保存进题目的图，删早了就是一张裂图。见 cleanup_media.py。
    media_retention_days: int = Field(default=30, ge=1, le=365)
    # 课包封面：与题干配图**分开存储**（用户明确要求新开一个区域）——语义不同、清理时
    # 扫描的引用列不同，混在 data/media 里两个清理口径会互相干扰。
    # URL 形如 /course-covers/ab/abcd….png，由 nginx 直发；大小/缩放上限复用 media_*。
    course_cover_upload_root: str = "data/course_covers"
    # 答疑附件始终经应用判权后下发，绝不作为静态公开目录暴露。
    help_attachment_upload_root: str = "data/help_attachments"
    help_attachment_max_bytes: int = Field(default=10 * 1024 * 1024, ge=1 * 1024 * 1024, le=20 * 1024 * 1024)
    help_attachment_retention_days: int = Field(default=30, ge=1, le=365)
    # 学生头像：独立存储区域（文档 28 P2）。绝不能并进 data/media——cleanup_media 的
    # _SCANNED_COLUMNS 不含 student_profiles.avatar_url，头像会被当孤儿清掉。
    # URL 形如 /avatars/ab/abcd….png，由 StaticFiles / nginx 直发；白名单格式与
    # 重编码复用 admin_media 的 _decode/_normalize，上限比题干配图收紧（头像是小图）。
    avatar_upload_root: str = "data/avatars"
    avatar_max_bytes: int = Field(default=2 * 1024 * 1024, ge=256 * 1024, le=5 * 1024 * 1024)
    avatar_max_dimension: int = Field(default=512, ge=256, le=1024)
    # 匿名发音代理：响应、频率和磁盘占用都必须有硬上限。默认值按短 MP3 设计，
    # 可由环境变量覆盖，但不能配置成无限制。
    typing_audio_cache_root: str = "data/audio_cache"
    typing_audio_response_max_bytes: int = Field(default=512 * 1024, ge=16 * 1024, le=2 * 1024 * 1024)
    typing_audio_cache_max_bytes: int = Field(default=256 * 1024 * 1024, ge=1 * 1024 * 1024, le=2 * 1024 * 1024 * 1024)
    typing_audio_cache_max_files: int = Field(default=5000, ge=100, le=100_000)
    typing_audio_rate_limit_per_minute: int = Field(default=120, ge=10, le=1000)
    typing_audio_fetch_limit_per_minute: int = Field(default=30, ge=5, le=300)
    # 学员端站点地址：拼完整考试链接（{exam_base_url}/exam/{access_token}）。
    # 为空时接口返回相对路径 /exam/{token}，由前端按当前域名自行拼全。
    exam_base_url: str = ""
    # 判题后端：fake = 不执行代码的假判题器（本地开发/CI 专用）；go-judge = 真沙箱。
    # go-judge 只监听回环，因此 judge_url 必须指向本机，见《判题沙箱搭建手册》。
    judge_backend: str = "fake"
    judge_url: str = "http://127.0.0.1:5050"
    judge_token: str = ""
    judge_timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    # 判题工作线程数。**吞吐不由它决定**——决定吞吐的是 go-judge 的 -parallelism。
    # 它只决定队列排在哪儿：排在我们进程里（看得见位次、能报排队中），还是排进
    # go-judge 内部（看不见，且单个 HTTP 可能逼近 judge_timeout_seconds）。
    # 取 ≈ 2× go-judge 的 -parallelism：正好 1 倍的话，任务在两次 HTTP 之间做本地
    # 处理时沙箱槽位会空转。线上 -parallelism=2，所以是 4。加内存提并行度时一起调。
    judge_workers: int = Field(default=4, ge=1, le=64)
    # 排队上限。超了直接 429，而不是让队列无限涨——那只会把等待变成超时。
    judge_queue_max: int = Field(default=500, ge=1, le=10_000)
    # 判题卡在 queued/judging 超过这个时长即认定为僵尸（多半是进程重启丢了在途任务），
    # 置 judge_failed。注意是 failed 不是 0 分：系统的锅不能算学员答错。
    judge_stale_seconds: int = Field(default=600, ge=30, le=7200)
    # 单个测试点文件读进内存的上限。testdata_unpacked_max_bytes 管的是整包，
    # 单个 .in 仍可能大到把判题机的 HTTP body 撑爆——超限按 judge_failed 处理。
    judge_case_max_bytes: int = Field(default=8 * 1024 * 1024, ge=64 * 1024, le=64 * 1024 * 1024)
    # 参考代码试跑的 diff 单字段截断长度。整个 10 万行的 .out 丢给前端会把浏览器卡死，
    # 所以只回差异行前后各 3 行，再按这个数截断。
    dry_run_field_max_chars: int = Field(default=2000, ge=200, le=20_000)
    # ============ MinIO / S3 对象存储（视频源与转码产物） ============
    # API 端口（默认 9000）。本地通过 SSH 隧道连腾讯云时填 http://127.0.0.1:9000，
    # 生产走内网域名 + TLS。应用用专用账号 app_uploader（readwrite），不用 root。
    minio_endpoint: str = "http://127.0.0.1:9000"
    minio_access_key: str = ""
    minio_secret_key: str = ""
    minio_use_ssl: bool = False
    # 浏览器能直连的 MinIO 公开端点（交接文档 17 批次1 S1-1b）。
    # 应用→MinIO 走 minio_endpoint（内网 / SSH 隧道），但给学生端签预签名 GET URL 必须用
    # 浏览器够得着的地址——S3v4 签名把 Host 签进去了，用内网地址签出来的 URL 浏览器换个
    # 域名访问会直接 403。本地开发填 http://127.0.0.1:9000（隧道直连，和应用同地址）；
    # 生产填 nginx 反代出去的公网域名。**空值时自动退回应用代理模式**，没配也不会挂。
    minio_public_endpoint: str = ""
    minio_source_bucket: str = "videos-source"  # 源文件桶
    minio_play_bucket: str = "videos-play"      # HLS 转码产物桶
    # 播放令牌签名密钥：与 MINIO_SECRET_KEY 分开。令牌只在应用内校验，永不下发到 MinIO。
    minio_play_secret: str = "change-me-video-play-secret"
    # 播放令牌有效期（分钟）。一个令牌覆盖整条 HLS 路径，学生一次播放会话内反复拉切片复用。
    video_token_minutes: int = Field(default=60, ge=5, le=1440)
    # ============ 视频观看时长记账（《20、视频观看时长服务端记账-设计》） ============
    # 心跳间隔（秒）：下发给前端，服务端不强制。改这个数要连带改 beat_cap（保持 ≈3 倍关系）。
    video_watch_heartbeat_seconds: int = Field(default=15, ge=5, le=60)
    # 单次心跳能认可的墙钟上限（秒）。**这是「攒时长攻击」的唯一防线**：
    # 没有它，开着页面干等 40 分钟再拖到片尾，一次请求就能兑现整部视频。
    # 取 ≈3× 心跳间隔：允许丢两拍（切后台/短暂断网）后补记，再多就不认了。
    video_watch_beat_cap_seconds: int = Field(default=45, ge=10, le=300)
    # 倍速容差。2.5 放行到 2x 播放；3x 播完账上只有 ~83%。
    # **调高它就是等比例调低作弊成本**（调到 4 = 支持 4x = 作弊只需 1/4 时长）。
    # 改之前先读设计文档 §9.1，并同步限制播放器的倍速选项，两边口径要一致。
    video_watch_tolerance: float = Field(default=2.5, ge=1.0, le=5.0)
    # 裁决权开关（批次 B3）。True = 视频块的完成只认服务端账本，客户端 complete 上报失效。
    # 灰度期留 False：前端心跳（B2）没全量之前就打开，老前端的学生视频块会完不成。
    video_watch_authoritative: bool = False
    # 单视频源文件上限。超限在「创建上传会话」阶段直接拒，不浪费一次 multipart。
    video_source_max_bytes: int = Field(default=2 * 1024 * 1024 * 1024, ge=10 * 1024 * 1024, le=20 * 1024 * 1024 * 1024)
    # 建议分片大小（前端 Uppy 用）。MinIO 单 part ≥ 5MB，这里给 64MB 让大视频 part 数可控。
    video_part_size: int = Field(default=64 * 1024 * 1024, ge=5 * 1024 * 1024, le=1024 * 1024 * 1024)
    # ============ 资料管理（资料库 + Windows 文件夹迁移） ============
    # 资料桶与视频桶隔离：资料生命周期（去重/引用保护/清理）与视频（转码/播放）互不干扰。
    minio_materials_bucket: str = "materials"
    # 单资料文件上限。资料不像视频动辄几个 GB，1GB 内覆盖绝大多数文档/图片/压缩包；
    # 超限在 init 阶段直接拒，不浪费一次 multipart。
    material_source_max_bytes: int = Field(default=1024 * 1024 * 1024, ge=1 * 1024 * 1024, le=5 * 1024 * 1024 * 1024)
    # 大文件分片建议大小。MinIO 单 part ≥ 5MB（最后一篇除外），16MB 让 part 数可控。
    material_part_size: int = Field(default=16 * 1024 * 1024, ge=5 * 1024 * 1024, le=256 * 1024 * 1024)
    # 单个迁移会话的清单总字节上限（配额控制，见交接文档 §8）。
    material_import_session_max_bytes: int = Field(
        default=20 * 1024 * 1024 * 1024, ge=1 * 1024 * 1024 * 1024, le=200 * 1024 * 1024 * 1024
    )
    # ============ Scratch 图形化编程（任务书 21b） ============
    # 学生 `.sb3` 与挑战初始项目的落盘根目录，内容寻址（`ab/<sha256>.sb3`）。
    # **不挂静态服务**：与题干配图（/media 由 nginx 直发）相反，作品是私有内容，
    # 一律经 `/api/scratch/...` 逐次鉴权后由应用读文件下发，存储路径不当权限凭证。
    scratch_upload_root: str = "data/scratch"
    # 单个 `.sb3` 上限。Scratch 项目带角色造型和声音，10MB 覆盖绝大多数课堂作品；
    # 超限在读请求体阶段就拒（多读 1 字节区分"正好等于"与"超了"，与图片上传同写法）。
    scratch_sb3_max_bytes: int = Field(default=10 * 1024 * 1024, ge=256 * 1024, le=100 * 1024 * 1024)
    # 解压后总字节上限（zip bomb 防线）。只查 ZIP 目录里声明的 file_size，不真解压。
    scratch_sb3_unpacked_max_bytes: int = Field(
        default=64 * 1024 * 1024, ge=1 * 1024 * 1024, le=512 * 1024 * 1024
    )
    # 压缩包内条目数上限。正常项目是 project.json + 几十个素材。
    scratch_sb3_max_entries: int = Field(default=500, ge=2, le=5000)
    # project.json 单文件上限：它要整个读进内存做 JSON 解析和规则匹配。
    scratch_project_json_max_bytes: int = Field(
        default=8 * 1024 * 1024, ge=64 * 1024, le=64 * 1024 * 1024
    )
    # 自动保存频率闸：每人每项目 scratch_save_rate_max 次 / scratch_save_rate_seconds 秒。
    # 默认 30/60s 足够 Studio 每 2 秒一次的高频自动保存，又挡得住脚本刷版本把磁盘写爆。
    scratch_save_rate_max: int = Field(default=30, ge=1, le=600)
    scratch_save_rate_seconds: int = Field(default=60, ge=10, le=3600)
    # 提交频率闸：判定是纯静态解析（无沙箱），但一次提交要解压 + 遍历全部积木，
    # 仍然按每人每块 10 次 / 5 分钟限速。
    scratch_submit_rate_max: int = Field(default=10, ge=1, le=200)
    scratch_submit_rate_seconds: int = Field(default=300, ge=10, le=3600)
    # ============ 转码（Celery + ffmpeg） ============
    # ffmpeg/ffprobe 所在目录（本地开发用下载的静态构建；生产服务器 apt 装的在 /usr/bin）。
    ffmpeg_bin_dir: str = "data/ffmpeg/bin"
    # 转码临时工作目录：下载源 + 本地 HLS 产物，转完即清。
    transcode_work_root: str = "data/transcode"

    @property
    def origins(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def trusted_proxies(self) -> list[str]:
        return [item.strip() for item in self.trusted_proxy_ips.split(",") if item.strip()]

    def validate_production(self) -> None:
        if self.environment != "production":
            return
        if not self.database_url.startswith(("postgresql://", "postgresql+psycopg://")):
            raise RuntimeError("Production requires a PostgreSQL DATABASE_URL.")
        if not self.redis_url or not self.cookie_secure or "*" in self.origins:
            raise RuntimeError("生产环境必须配置 Redis、Secure Cookie 和精确的 CORS_ORIGINS。")
        production_secrets = (
            self.jwt_secret_key,
            self.jwt_previous_secret_key,
            self.refresh_token_hmac_key,
            self.verification_hmac_key,
            self.outbox_encryption_key,
        )
        if (
            not self.origins
            or any(_is_production_secret_rejected(value) for value in production_secrets)
            or self.outbox_encryption_key == DEV_FERNET_KEY
            or self.jwt_previous_secret_key == self.jwt_secret_key
        ):
            raise RuntimeError("生产环境不得使用开发密钥、公开示例或占位密钥；current/previous 也不得重复。")
        if not self.pwned_check_enabled or not self.pwned_check_strict:
            raise RuntimeError(
                "生产环境必须启用严格的泄露密码检查；请配置可用的 PWNED_API_BASE_URL。"
            )
        if not all((self.smtp_host, self.smtp_username, self.smtp_password, self.smtp_from)):
            raise RuntimeError("生产环境必须配置企业 SMTP。")
        # 假判题器只看代码里有没有 print/cout，不看正确性。上了生产就是所有编程题白送分。
        if self.judge_backend != "go-judge":
            raise RuntimeError("生产环境必须配置真实判题沙箱（JUDGE_BACKEND=go-judge）。")
        # 视频模块：生产必须配真实 MinIO 凭据、TLS，以及独立的播放令牌密钥。
        if not self.minio_access_key or not self.minio_secret_key or self.minio_play_secret.startswith("change-me"):
            raise RuntimeError("生产环境必须配置 MinIO 凭据与播放令牌密钥（MINIO_* / MINIO_PLAY_SECRET）。")
        if self.minio_use_ssl is False:
            raise RuntimeError("生产环境 MinIO 必须启用 TLS（MINIO_USE_SSL=true）。")
        # 相对路径在生产会跟着 systemd 的 WorkingDirectory 跑，重启一次换个目录，
        # 已上传的图就集体 404 了。与 testdata 同一条要求。
        for label, value in (("MEDIA_UPLOAD_ROOT", self.media_upload_root),
                             ("COURSE_COVER_UPLOAD_ROOT", self.course_cover_upload_root),
                             ("AVATAR_UPLOAD_ROOT", self.avatar_upload_root),
                             ("SCRATCH_UPLOAD_ROOT", self.scratch_upload_root),
                             ("TESTDATA_UPLOAD_ROOT", self.testdata_upload_root),
                             ("TYPING_AUDIO_CACHE_ROOT", self.typing_audio_cache_root)):
            if not Path(value).is_absolute():
                raise RuntimeError(f"生产环境的 {label} 必须是绝对路径。")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_production()
    return settings
