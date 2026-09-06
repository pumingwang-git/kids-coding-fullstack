# 学习平台后端（FastAPI + Celery 转码 worker 共用此镜像）
# ffmpeg 供 Celery 转码任务使用；backend 与 celery 用同一镜像，靠 command 区分角色。
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

# ffmpeg/ffprobe：转码；curl：健康检查。
# 弱网/代理环境下 apt 易断流：加多次重试 + 关闭 HTTP 管道（逐个下载更稳）+ 拉长超时。
RUN printf 'Acquire::Retries "12";\nAcquire::http::Timeout "60";\nAcquire::http::Pipeline-Depth "0";\n' \
        > /etc/apt/apt.conf.d/80-retries \
    && apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# 上传落盘根目录（/media、/avatars、转码临时区等都在 data 下；用命名卷持久化）
RUN mkdir -p data/transcode data/media data/course_covers data/avatars \
             data/testdata data/scratch data/audio_cache data/help_attachments

EXPOSE 8000

# 默认以 API 角色启动；compose 里会覆盖为「先迁移再起服务」，celery 角色另给 command。
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
