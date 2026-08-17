"""视频模块回归：播放签名、流代理、播放列表改写、上传会话状态机、转码失败置 failed。

本文件用 monkeypatch 把 MinIO / Celery / ffmpeg 外部依赖钉死，不依赖真实对象存储：
- 播放签名（P2-5）：sign/verify 正常、换 URI、换用户、篡改、过期、缺参；
  deadline 时间片量化（同片内恒定 = URL 稳定 = 浏览器缓存能命中）；
- 播放列表改写：m3u8 子 URI 逐条补签名，且补出来的地址真能过校验
  （播放器不会把父 URL 的 query 继承给子列表和切片，漏改写就在第一跳 403）；
- 流代理：坏签名 403、对象不存在 404、Range 请求 206 且 Content-Range 用
  S3 ContentRange 的完整总长（不能用分片 ContentLength，seek 会算错）；
- 上传会话：create 201 → presign → complete（ETag 由服务端核对）→ abort 幂等，
  ETag 不匹配 409；
- 转码：MinIO 不可达 → eager 模式异常向上抛，且 video.status 置 failed。
"""
import io
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_admin_courses import add_section, create_category, create_course
from test_exam import admin_login, build_app, scsrf, student_login
from test_student_learning import seed_ready_video

from app import video_sign
from app.database import build_database
from app.models import Video, VideoUpload
from app.s3_multipart import play_token_minutes

# ----------------------------- 播放令牌 TTL -----------------------------

def test_play_token_minutes_clamp():
    """TTL = 时长 + 10 分钟，clamp 到 [60, 240]；时长未知回落默认值。"""
    # 短视频 → 至少 60 分钟
    assert play_token_minutes(300, 60) == 60          # 5min + 10 = 15 → clamp 60
    assert play_token_minutes(60, 60) == 60           # 1min + 10 = 11 → clamp 60
    # 正常时长 → 时长 + 10
    assert play_token_minutes(3600, 60) == 70         # 60min + 10
    assert play_token_minutes(7200, 60) == 130        # 120min + 10
    # 超长视频 → 封顶 240 分钟
    assert play_token_minutes(6 * 3600, 60) == 240    # 360 + 10 → clamp 240
    assert play_token_minutes(24 * 3600, 60) == 240
    # 时长未知（转码中/未填）→ 默认值
    assert play_token_minutes(None, 60) == 60
    assert play_token_minutes(0, 60) == 60
    assert play_token_minutes(-1, 60) == 60


def test_mint_play_url_ttl_scales_with_duration(tmp_path: Path):
    """签发响应的 expires_in_seconds 与视频时长联动（评审：超过 1 小时视频不能中途失效）。

    P2-5 起过期时刻被对齐到时间片（video_sign.quantized_deadline），所以不再断言精确值：
    要钉住的是「**绝不短于** 时长+10 分钟」——量化只会多给，不会少给，
    少给就意味着长视频可能播到一半失效，那正是这条用例当初要防的。
    """
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    cat = create_category(client, headers).json()
    cid = create_course(client, headers, cat["id"]).json()["id"]
    section = add_section(client, headers, cid, "第一章").json()
    video = seed_ready_video(app, title="长视频")
    # 模拟一条 90 分钟的视频
    db = app.state.session_factory()
    try:
        v = db.get(Video, video["video_id"])
        v.duration_seconds = 90 * 60
        db.commit()
    finally:
        db.close()
    lesson = client.post(f"/api/admin/sections/{section['id']}/lessons", headers=headers,
                         json={"title": "课时", "video_id": video["video_id"], "is_trial": True}).json()
    assert client.post(f"/api/admin/courses/{cid}/publish", headers=headers).status_code == 200

    sclient = student_login(app)
    resp = sclient.post(f"/api/lessons/{lesson['id']}/play", headers=scsrf(sclient))
    assert resp.status_code == 200, resp.text
    ttl = resp.json()["expires_in_seconds"]
    assert ttl >= 100 * 60  # 90min + 10 = 100min，这是下限
    assert ttl < 100 * 60 + 2 * video_sign.BUCKET_SECONDS  # 量化的宽限有上限


# ----------------------------- 播放签名（P2-5） -----------------------------

def test_signature_wire_format_matches_nginx():
    """把签名的**线上格式**钉死：待签串与 nginx secure_link_md5 必须逐字符一致。

    这条不是在测 Python 自洽（那是 sign/verify 的事），而是测「Python 和 nginx 算的是
    同一个东西」。部署配置/nginx-cache.conf 里写的是：

        secure_link     $arg_s,$arg_e;
        secure_link_md5 "$secure_link_expires$uri$arg_u SECRET";

    即 md5("{e}{uri}{u} {secret}") 的 16 字节摘要做 base64url、去掉 = 填充。
    任何人改动 _digest 的拼接顺序、分隔符或编码，这条会红，并直接指向要同步改的
    nginx 配置——否则线上表现是「切片全 403」，而单测全绿。
    """
    import base64
    import hashlib

    secret = "s3cr3t"
    uri = "/v/12/720p/seg_00001.ts"
    uid = "37"
    expires = 1786000000

    expected = base64.urlsafe_b64encode(
        hashlib.md5(f"{expires}{uri}{uid} {secret}".encode()).digest()
    ).decode().rstrip("=")

    assert video_sign.sign(secret, uri, uid, expires) == expected
    assert len(expected) == 22  # 16 字节摘要的 base64 长度，nginx 也是这个长度
    # query 的参数名与顺序同样是对外契约（nginx 读 $arg_e/$arg_u/$arg_s）
    assert video_sign.signed_query(secret, uri, uid, expires) == (
        f"e={expires}&u={uid}&s={expected}"
    )


def test_sign_verify_lifecycle(tmp_path: Path):
    """正常放行；换 URI / 换用户 / 篡改签名 / 过期 / 缺参一律拒绝。"""
    app = build_app(tmp_path)
    secret = app.state.settings.minio_play_secret
    uri = "/v/7/720p/seg_00001.ts"
    exp = int(time.time()) + 600
    sig = video_sign.sign(secret, uri, 37, exp)

    assert video_sign.verify(secret, uri, "37", exp, sig) is True

    # 换一条 URI 用同一个签名：路径被签进去了，挪不动
    assert video_sign.verify(secret, "/v/7/720p/seg_00002.ts", "37", exp, sig) is False
    # 跨视频同样挪不动
    assert video_sign.verify(secret, "/v/8/720p/seg_00001.ts", "37", exp, sig) is False
    # 换用户：URL 是按 uid 签的，转发给同学也用不了
    assert video_sign.verify(secret, uri, "38", exp, sig) is False
    # 篡改签名 / 篡改过期时间
    assert video_sign.verify(secret, uri, "37", exp, "x" * 22) is False
    assert video_sign.verify(secret, uri, "37", exp + 1, sig) is False
    # 过期（签名本身有效，只是时间到了）
    old = int(time.time()) - 10
    assert video_sign.verify(secret, uri, "37", old, video_sign.sign(secret, uri, 37, old)) is False
    # 缺参 / 畸形
    assert video_sign.verify(secret, uri, "37", exp, None) is False
    assert video_sign.verify(secret, uri, None, exp, sig) is False
    assert video_sign.verify(secret, uri, "37", "not-a-number", sig) is False


def test_deadline_quantized_and_stable():
    """时间片量化：同一片内取值恒定（URL 才稳定），且有效期绝不短于申请的 TTL。

    这是 P2-5 里「浏览器缓存能跨刷新命中」的全部理由——签名在 query，
    e 每次不同就等于 URL 每次不同，缓存必然 miss。
    """
    b = video_sign.BUCKET_SECONDS
    base = 1_800_000_000  # 恰好落在时间片边界上，便于推算
    ttl = 3600

    # 同一时间片内的任意时刻 → 同一个 deadline
    d0 = video_sign.quantized_deadline(ttl, now=base)
    assert video_sign.quantized_deadline(ttl, now=base + 1) == d0
    assert video_sign.quantized_deadline(ttl, now=base + b - 1) == d0
    # 跨到下一片 → 换一个 deadline（否则有效期会被越切越短）
    assert video_sign.quantized_deadline(ttl, now=base + b) == d0 + b

    # 有效期不短于 ttl，且超出不超过两个时间片（量化的代价，上限必须可控）
    for offset in (0, 1, b // 2, b - 1):
        now = base + offset
        life = video_sign.quantized_deadline(ttl, now=now) - now
        assert life >= ttl
        assert life < ttl + 2 * b


def test_play_urls_stable_within_bucket(tmp_path: Path):
    """同一用户同一视频，在同一时间片内两次签发拿到**逐字节相同**的地址。

    这条一红，「切走再切回 / F5 不再重下」就没了——浏览器缓存键包含 query，
    地址只要有一个字符不同就是全新资源。
    """
    app = build_app(tmp_path)
    secret = app.state.settings.minio_play_secret
    base = 1_800_000_000
    a = video_sign.playback_urls(secret, 12, 37, ["720p"], 3600, now=base + 5)
    c = video_sign.playback_urls(secret, 12, 37, ["720p"], 3600, now=base + 900)
    assert a["master_playlist"] == c["master_playlist"]
    assert a["variants_urls"] == c["variants_urls"]

    # 换个用户必须换地址（否则 uid 就白签了，日志也追不到人）
    other = video_sign.playback_urls(secret, 12, 38, ["720p"], 3600, now=base + 5)
    assert other["master_playlist"] != a["master_playlist"]


# ----------------------------- 流代理 -----------------------------

def signed_path(app, video_id, rel_path: str, uid: int = 1, ttl: int = 600) -> str:
    """按新口径拼一个带签名的播放地址（测试里到处要用）。"""
    secret = app.state.settings.minio_play_secret
    uri = video_sign.stream_uri(video_id, rel_path)
    return video_sign.signed_url(secret, uri, uid, int(time.time()) + ttl)


def test_stream_rejects_bad_signature(tmp_path: Path):
    """签名无效 / 缺失 / 过期 / 挪用 → 403（校验在访问 MinIO 之前，不依赖存储）。"""
    app = build_app(tmp_path)
    v = seed_ready_video(app)
    client = TestClient(app)
    vid = v["video_id"]

    # 完全没有签名参数
    assert client.get(f"/v/{vid}/master.m3u8").status_code == 403
    # 伪造签名
    exp = int(time.time()) + 600
    assert client.get(f"/v/{vid}/master.m3u8?e={exp}&u=1&s={'x' * 22}").status_code == 403
    # 签名有效但已过期
    assert client.get(signed_path(app, vid, "master.m3u8", ttl=-10)).status_code == 403
    # 拿这个视频的签名去取另一个视频
    stolen = signed_path(app, vid, "master.m3u8")
    assert client.get(stolen.replace(f"/v/{vid}/", f"/v/{vid + 1}/", 1)).status_code == 403


def test_stream_object_missing_404(tmp_path: Path, monkeypatch):
    """签名有效但对象不存在 → 404（不再查库：签名就是凭证，路径直接映射对象键）。"""
    app = build_app(tmp_path)
    from types import SimpleNamespace

    def boom(**kwargs):
        raise KeyError("no such key")

    monkeypatch.setattr(
        "app.routers.video_play.get_minio_client",
        lambda settings: SimpleNamespace(get_object=boom),
    )
    client = TestClient(app)
    assert client.get(signed_path(app, 99999, "master.m3u8")).status_code == 404


def _fake_minio(monkeypatch, body: bytes):
    from types import SimpleNamespace

    monkeypatch.setattr(
        "app.routers.video_play.get_minio_client",
        lambda settings: SimpleNamespace(get_object=lambda **kw: {"Body": io.BytesIO(body)}),
    )


def test_playlist_rewritten_with_signed_children(tmp_path: Path, monkeypatch):
    """m3u8 的每条子 URI 都被补上签名，且沿用父请求的 e/u。

    这是整个方案能跑起来的关键：播放器不会把 master 上的 query 继承给子列表和切片
    （HLS 里 URI 按 RFC 3986 相对解析，query 不参与继承），不改写就会在第一个
    子请求上 403。
    """
    app = build_app(tmp_path)
    secret = app.state.settings.minio_play_secret
    master = "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1000000\n720p/index.m3u8\n"
    _fake_minio(monkeypatch, master.encode())

    exp = int(time.time()) + 600
    uri = video_sign.stream_uri(12, "master.m3u8")
    resp = TestClient(app).get(video_sign.signed_url(secret, uri, 37, exp))

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/vnd.apple.mpegurl")
    # 子列表改写成绝对路径 + 签名，e/u 与父请求一致（整条会话共用一个过期时刻）
    expected = video_sign.signed_url(secret, "/v/12/720p/index.m3u8", 37, exp)
    assert expected in resp.text
    # 标签行原样保留，不能被当成 URI 签掉
    assert "#EXT-X-STREAM-INF:BANDWIDTH=1000000" in resp.text


def test_playlist_child_signature_actually_works(tmp_path: Path, monkeypatch):
    """改写出来的子地址必须真能过校验——只断言「长得像」会漏掉拼接口径不一致。"""
    app = build_app(tmp_path)
    secret = app.state.settings.minio_play_secret
    _fake_minio(monkeypatch, b"#EXTM3U\n#EXTINF:6.0,\nseg_00001.ts\n#EXT-X-ENDLIST\n")

    exp = int(time.time()) + 600
    uri = video_sign.stream_uri(12, "720p/index.m3u8")
    resp = TestClient(app).get(video_sign.signed_url(secret, uri, 37, exp))
    assert resp.status_code == 200

    seg_line = next(ln for ln in resp.text.splitlines() if ln.startswith("/v/"))
    path, query = seg_line.split("?", 1)
    assert path == "/v/12/720p/seg_00001.ts"  # 相对路径按父列表所在目录解析
    params = dict(p.split("=", 1) for p in query.split("&"))
    assert video_sign.verify(secret, path, params["u"], params["e"], params["s"]) is True


def test_stream_range_206_uses_full_length(tmp_path: Path, monkeypatch):
    """Range 请求 → 206，且 Content-Range 总长取 S3 ContentRange（完整对象长度）。

    回归评审 P0：原实现用 ContentLength（本次分片字节数）当 total，seek 场景会
    返回错误 Content-Range，客户端据此拼下一段 Range 会 416 或漏段。
    """
    app = build_app(tmp_path)
    v = seed_ready_video(app)

    class FakeBody:
        def __iter__(self):
            return iter([b"0123456789"])

    def fake_get_object(**kwargs):
        return {
            "Body": FakeBody(),
            "ContentLength": 10,                 # 分片长度 ≠ 完整长度
            "ContentRange": "bytes 0-9/5000",    # 完整对象 5000 字节
            "ContentType": "video/mp2t",
        }

    # 用 SimpleNamespace 而非 type()：类实例访问方法会触发描述符绑定，
    # 把实例当第一参数传进去，签名不匹配直接 TypeError（被 stream 的 except 吞成 404）。
    from types import SimpleNamespace

    monkeypatch.setattr(
        "app.routers.video_play.get_minio_client",
        lambda settings: SimpleNamespace(get_object=fake_get_object),
    )

    resp = TestClient(app).get(
        signed_path(app, v["video_id"], "720p/seg_00001.ts"),
        headers={"Range": "bytes=0-9"},
    )
    assert resp.status_code == 206
    assert resp.headers["Content-Range"] == "bytes 0-9/5000"
    # 切片是不可变内容，缓存到签名过期为止——F5 之后不再重下靠的就是这条
    assert "immutable" in resp.headers["Cache-Control"]


def test_stream_range_open_ended_uses_s3_end(tmp_path: Path, monkeypatch):
    """P0-1 回归：Range: bytes=start-（open-ended）时 Content-Range 结束值不越界。

    旧实现 end = start + total - 1：start=100、total=5000 会算出 5099（超出文件尾），
    播放器据此拼下一段 Range 会 416 或反复重试。修复后直接透传 S3 返回的
    ContentRange（end 是 S3 实际返回的最后字节 = total - 1）。
    """
    app = build_app(tmp_path)
    v = seed_ready_video(app)

    class FakeBody:
        def __iter__(self):
            return iter([b"x" * 10])

    def fake_get_object(**kwargs):
        assert kwargs["Range"] == "bytes=100-"  # 向后端请求的原始 Range 原样透传
        return {
            "Body": FakeBody(),
            "ContentLength": 10,
            "ContentRange": "bytes 100-109/5000",  # S3 返回的 end = 109（已到文件尾）
            "ContentType": "video/mp2t",
        }

    from types import SimpleNamespace

    monkeypatch.setattr(
        "app.routers.video_play.get_minio_client",
        lambda settings: SimpleNamespace(get_object=fake_get_object),
    )

    resp = TestClient(app).get(
        signed_path(app, v["video_id"], "720p/seg_00001.ts"),
        headers={"Range": "bytes=100-"},
    )
    assert resp.status_code == 206
    # 越界旧值会是 "bytes 100-5099/5000"；正确值是 S3 给的 end
    assert resp.headers["Content-Range"] == "bytes 100-109/5000"


def test_private_json_no_store(tmp_path: Path):
    """P0-2 回归：带身份的 JSON 接口必须显式 Cache-Control: private, no-store。

    不能依赖浏览器对 JSON 的默认行为，也不能让生产 Nginx/CDN 误缓存 /api/ 与 /v/。
    中间件只对 application/json 生效——视频/资料二进制流不受影响（它们各自带
    private, max-age，见 test_stream_range_206_uses_full_length）。
    """
    app = build_app(tmp_path)
    client = student_login(app)
    resp = client.get("/api/auth/me")
    assert resp.status_code == 200
    assert resp.headers["Cache-Control"] == "private, no-store"

    # 课时详情（带解锁状态/进度）同样命中
    courses = client.get("/api/courses")
    assert courses.status_code == 200
    assert courses.headers["Cache-Control"] == "private, no-store"


# ----------------------------- 上传会话状态机 -----------------------------

def test_upload_session_flow(tmp_path: Path, monkeypatch):
    """create → presign → complete（ETag 服务端核对）→ abort 幂等。"""
    app = build_app(tmp_path)
    client, headers = admin_login(app)

    calls: dict = {}
    seq = {"n": 0}  # upload_id 计数必须跨实例共享：端点每次调用 get_minio_client 都新建 FakeMinio

    class FakeMinio:
        def create_multipart_upload(self, **kwargs):
            calls["created"] = kwargs
            seq["n"] += 1
            return {"UploadId": f"up-{seq['n']}"}

        def generate_presigned_url(self, *a, **kwargs):
            return "https://minio.local/presigned/1"

        def list_parts(self, **kwargs):
            # 服务端「不信前端」：这里模拟 MinIO 里真实已传的分片
            return {"Parts": [{"PartNumber": 1, "ETag": '"abc"'}]}

        def complete_multipart_upload(self, **kwargs):
            calls["completed"] = kwargs

        def abort_multipart_upload(self, **kwargs):
            calls["aborted"] = kwargs

    monkeypatch.setattr("app.s3_multipart.get_minio_client", lambda settings: FakeMinio())

    class FakeTask:
        def delay(self, video_id):
            calls["transcode_scheduled"] = video_id

    # complete 会经 BackgroundTasks 同步调度转码（eager），先钉死转码入口
    monkeypatch.setattr("app.tasks.transcode.transcode_video", FakeTask())

    # —— 会话 A：取消路径 ——
    resp = client.post("/api/admin/videos/uploads", headers=headers, json={
        "title": "第一课", "filename": "lesson.mp4",
        "content_type": "video/mp4", "file_size": 1024 * 1024,
    })
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["upload_id"] == "up-1"
    assert body["part_count"] >= 1
    upload_id = body["upload_id"]

    # presign part
    presign = client.get(f"/api/admin/videos/uploads/{upload_id}/parts/1", headers=headers)
    assert presign.status_code == 200
    assert presign.json()["url"].startswith("https://")

    # ETag 不匹配 → 409（前端自报的不信）。必须在正常 complete 之前测：
    # complete 成功后会话状态变 completed，_load_upload 会返回 404。
    resp = client.post(f"/api/admin/videos/uploads/{upload_id}/complete", headers=headers,
                       json={"parts": [{"part_number": 1, "etag": '"xyz"'}]})
    assert resp.status_code == 409

    # 取消上传 → 200，再取消 → 404（会话已结束）
    assert client.post(f"/api/admin/videos/uploads/{upload_id}/abort", headers=headers).status_code == 200
    assert client.post(f"/api/admin/videos/uploads/{upload_id}/abort", headers=headers).status_code == 404

    # —— 会话 B：完成路径 ——
    resp = client.post("/api/admin/videos/uploads", headers=headers, json={
        "title": "第二课", "filename": "lesson2.mp4",
        "content_type": "video/mp4", "file_size": 1024 * 1024,
    })
    assert resp.status_code == 201
    complete_upload_id = resp.json()["upload_id"]
    complete = client.post(f"/api/admin/videos/uploads/{complete_upload_id}/complete", headers=headers,
                           json={"parts": [{"part_number": 1, "etag": '"abc"'}]})
    assert complete.status_code == 200, complete.text
    assert complete.json()["status"] == "uploaded"
    assert calls["transcode_scheduled"] == resp.json()["video_id"]
    # 已完成会话不可再 abort（404，幂等防误操作）
    assert client.post(f"/api/admin/videos/uploads/{complete_upload_id}/abort",
                       headers=headers).status_code == 404


def test_upload_rejects_oversize(tmp_path: Path, monkeypatch):
    """超限源文件 413，且不触碰 MinIO。"""
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    huge = app.state.settings.video_source_max_bytes + 1

    resp = client.post("/api/admin/videos/uploads", headers=headers, json={
        "title": "超限", "filename": "big.mp4", "content_type": "video/mp4",
        "file_size": huge,
    })
    assert resp.status_code == 413


# ----------------------------- 转码失败路径 -----------------------------

def test_transcode_failure_marks_failed(tmp_path: Path, monkeypatch):
    """MinIO 不可达 → eager 模式异常向上抛，video.status 置 failed（供后台标红）。"""
    app = build_app(tmp_path)
    settings = app.state.settings
    db = app.state.session_factory()
    try:
        video = Video(title="t", status="uploaded")
        db.add(video)
        db.commit()
        db.add(VideoUpload(
            video_id=video.id, uploader_id=1, bucket=settings.minio_source_bucket,
            object_key="a/b.mp4", upload_id="up-x", status="completed", file_size=10,
        ))
        db.commit()
        video_id = video.id
    finally:
        db.close()

    # 任务内部自己建 DB 连接、自己读配置——全部钉到测试环境
    monkeypatch.setattr("app.tasks.transcode.get_settings", lambda: settings)
    monkeypatch.setattr("app.tasks.transcode.build_database",
                        lambda url: build_database(settings.database_url))
    monkeypatch.setattr("app.tasks.transcode.get_minio_client",
                        lambda settings: (_ for _ in ()).throw(RuntimeError("minio down")))

    from app.tasks.transcode import transcode_video

    with pytest.raises(RuntimeError):
        transcode_video.apply(args=[video_id])  # eager 模式传播异常

    db = app.state.session_factory()
    try:
        assert db.get(Video, video_id).status == "failed"
    finally:
        db.close()
