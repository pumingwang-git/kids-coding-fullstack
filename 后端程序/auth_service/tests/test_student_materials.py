"""学生端资料下载/预览接口（交接文档 15 §7.3，S1）。

覆盖：
- 非本块绑定 material_id → 404（路径带上下文的红线：换块/换课时都拿不到）；
- 块被两道闸门任一锁住 → 403（not_enrolled / sequential）；
- MaterialAsset.status != ready → 404；
- download → Content-Disposition attachment + filename*，inline → Content-Disposition inline；
- 响应体就是文件内容，不含 object_key；Content-Type == asset.mime_type；
- 未登录 → 401。

测试环境没有 MinIO：monkeypatch app.s3_multipart.get_minio_client 为 FakeS3Client
（内存对象存储），照抄 test_admin_materials.py 的惯例。
"""
from pathlib import Path
from urllib.parse import unquote

from test_admin_course_content import build_lesson_without_content
from test_admin_materials import (
    bind_fake,
    create_materials_block,
    fake_s3,
    seed_ready_asset,
)
from test_exam import admin_login, build_app, student_login

from app.models import CourseLesson, MaterialAsset

PDF_CONTENT = b"%PDF-1.4 fake body for student download tests"


def _set_trial_whole(app, lesson_id: int) -> None:
    """设为试看课时（open_policy=whole）：未开通学生也能解锁，方便测业务分支。"""
    db = app.state.session_factory()
    try:
        row = db.get(CourseLesson, lesson_id)
        row.is_trial = True
        row.open_policy = "whole"
        db.commit()
    finally:
        db.close()


def _seed_asset(app, display_name: str, mime_type: str, content: bytes,
                status: str = "ready") -> dict:
    """照 seed_ready_asset，但 mime_type 可指定（细分依赖 mime_type，见文档 §7.1）。"""
    import hashlib

    db = app.state.session_factory()
    try:
        key = f"materials/seed/{display_name}"
        fake = getattr(app.state, "_fake_s3", None)
        if fake is not None and status == "ready":
            fake.objects[key] = content
        asset = MaterialAsset(
            folder_id=None, display_name=display_name, object_key=key,
            mime_type=mime_type, asset_type="document",
            size_bytes=len(content), sha256=hashlib.sha256(content).hexdigest(),
            status=status,
        )
        db.add(asset)
        db.commit()
        return {"asset_id": asset.id, "object_key": key}
    finally:
        db.close()


def _bind(app, client, headers, block_id: int, asset_id: int) -> None:
    resp = client.post(f"/api/admin/lesson-blocks/{block_id}/materials", headers=headers,
                       json={"material_ids": [asset_id]})
    assert resp.status_code == 201, resp.text


def _create_block(client, headers, lesson_id: int, *,
                  unlock_rule: str = "free", required: bool = True) -> dict:
    """建 materials 块，可指定 Gate B 参数（create_materials_block 不带这两个字段）。"""
    resp = client.post(f"/api/admin/lessons/{lesson_id}/blocks", headers=headers,
                       json={"block_type": "materials", "title": "阅读资料",
                             "required": required, "unlock_rule": unlock_rule})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _ready_lesson(app, client, headers, asset_id: int | None = None):
    """建已发布的试看课时 + 一个 materials 块（可先绑一份资料，发布检查会拦截空块）。

    发布后禁止再增改内容块（护栏），所以测试要加第二个块/第二份资料都得在发布前做完。
    """
    _, _, course, _, lesson = build_lesson_without_content(app)
    block = create_materials_block(client, headers, lesson["id"])
    if asset_id is not None:
        _bind(app, client, headers, block["id"], asset_id)
    assert client.post(f"/api/admin/courses/{course['id']}/publish",
                       headers=headers).status_code == 200
    _set_trial_whole(app, lesson["id"])
    return lesson, block


def test_anonymous_visitor_is_401(tmp_path: Path, fake_s3):
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    bind_fake(app, fake_s3)
    asset = seed_ready_asset(app, "讲义.pdf", content=PDF_CONTENT)
    lesson, block = _ready_lesson(app, client, headers, asset_id=asset["asset_id"])
    from fastapi.testclient import TestClient

    resp = TestClient(app).get(
        f"/api/lessons/{lesson['id']}/blocks/{block['id']}/materials/{asset['asset_id']}/download"
    )
    assert resp.status_code == 401


def test_download_and_inline_headers_and_body(tmp_path: Path, fake_s3):
    """两种 Content-Disposition 正确；响应体就是对象内容且不含 object_key；mime_type 透传。"""
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    bind_fake(app, fake_s3)
    asset = _seed_asset(app, "讲义.pdf", mime_type="application/pdf", content=PDF_CONTENT)
    lesson, block = _ready_lesson(app, client, headers, asset_id=asset["asset_id"])

    stu = student_login(app)
    url = f"/api/lessons/{lesson['id']}/blocks/{block['id']}/materials/{asset['asset_id']}"

    dl = stu.get(f"{url}/download")
    assert dl.status_code == 200, dl.text
    assert dl.headers["content-disposition"].startswith("attachment;")
    assert "filename*=UTF-8''" in dl.headers["content-disposition"]
    # filename* 是 RFC 5987 百分号编码，解回来应含原始文件名
    assert "讲义.pdf" in unquote(dl.headers["content-disposition"])
    assert dl.headers["content-type"].startswith("application/pdf")
    assert dl.content == PDF_CONTENT
    assert b"object_key" not in dl.content  # 对象存储位置是内部细节，不下发

    inline = stu.get(f"{url}/inline")
    assert inline.status_code == 200, inline.text
    assert inline.headers["content-disposition"].startswith("inline;")
    assert inline.headers["content-type"].startswith("application/pdf")
    assert inline.content == PDF_CONTENT


def test_inline_range_requests(tmp_path: Path, fake_s3):
    """P0-1 回归：资料代理的 Content-Range 结束值不越界（PDF.js 分段取页靠它）。

    旧实现 end = start + total - 1：open-ended `bytes=start-` 下 total 是**完整对象
    长度**，再叠加 start 必然超出文件尾（start>0 时），PDF 阅读器据此拼下一段 Range
    会 416 或反复重试——表现就是"每次都要重新加载"。修复后透传 S3 的 ContentRange。
    """
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    bind_fake(app, fake_s3)
    asset = _seed_asset(app, "讲义.pdf", mime_type="application/pdf", content=PDF_CONTENT)
    lesson, block = _ready_lesson(app, client, headers, asset_id=asset["asset_id"])
    stu = student_login(app)
    url = (f"/api/lessons/{lesson['id']}/blocks/{block['id']}"
           f"/materials/{asset['asset_id']}/inline")
    total = len(PDF_CONTENT)

    # ① open-ended：越界回归就在这条。旧值会是 bytes 10-{10+total-1}/{total}
    resp = stu.get(url, headers={"Range": "bytes=10-"})
    assert resp.status_code == 206
    assert resp.headers["Content-Range"] == f"bytes 10-{total - 1}/{total}"
    assert resp.headers["Content-Length"] == str(total - 10)
    assert resp.content == PDF_CONTENT[10:]

    # ② 闭区间：结束值与总长都照实
    resp = stu.get(url, headers={"Range": "bytes=0-9"})
    assert resp.status_code == 206
    assert resp.headers["Content-Range"] == f"bytes 0-9/{total}"
    assert resp.content == PDF_CONTENT[:10]

    # ③ 无 Range：仍是完整 200，且声明支持 Range（PDF.js 据此才会分段取）
    resp = stu.get(url)
    assert resp.status_code == 200
    assert resp.headers["Accept-Ranges"] == "bytes"
    assert resp.content == PDF_CONTENT


def test_material_not_bound_to_this_block_404(tmp_path: Path, fake_s3):
    """红线：换一个不属于本块的 material_id → 404；不存在 id 同样 404。"""
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    bind_fake(app, fake_s3)
    asset_a = seed_ready_asset(app, "本块资料.pdf", content=PDF_CONTENT)
    asset_b = seed_ready_asset(app, "别人的资料.pdf", content=PDF_CONTENT)
    _, _, course, _, lesson = build_lesson_without_content(app)
    block = create_materials_block(client, headers, lesson["id"])
    other = _create_block(client, headers, lesson["id"])
    _bind(app, client, headers, block["id"], asset_a["asset_id"])
    _bind(app, client, headers, other["id"], asset_b["asset_id"])
    assert client.post(f"/api/admin/courses/{course['id']}/publish",
                       headers=headers).status_code == 200
    _set_trial_whole(app, lesson["id"])

    stu = student_login(app)
    # 绑在 other 块上，却从 block 取 → 404
    resp = stu.get(
        f"/api/lessons/{lesson['id']}/blocks/{block['id']}/materials/{asset_b['asset_id']}/download"
    )
    assert resp.status_code == 404
    # 完全不存在的 material_id → 404
    resp = stu.get(
        f"/api/lessons/{lesson['id']}/blocks/{block['id']}/materials/999999/download"
    )
    assert resp.status_code == 404


def test_unknown_lesson_or_block_404(tmp_path: Path, fake_s3):
    """课时不存在 / 块不属于该课时 → 404（与 courses.py 的 complete_block 同口径）。"""
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    bind_fake(app, fake_s3)
    asset = seed_ready_asset(app, "讲义.pdf", content=PDF_CONTENT)
    lesson, block = _ready_lesson(app, client, headers, asset_id=asset["asset_id"])

    stu = student_login(app)
    assert stu.get(
        f"/api/lessons/999999/blocks/{block['id']}/materials/{asset['asset_id']}/download"
    ).status_code == 404
    assert stu.get(
        f"/api/lessons/{lesson['id']}/blocks/999999/materials/{asset['asset_id']}/download"
    ).status_code == 404


def test_presign_material_get_reuses_url_within_ttl(monkeypatch):
    """预签名 URL 复用缓存：TTL 窗口内同一 (bucket,key,disposition) 只签一次、
    返回同一 URL（浏览器 HTTP 缓存才能命中）；不同参数或缓存过期后重签。"""
    import time

    import app.s3_multipart as sm

    calls = []

    class FakeClient:
        def generate_presigned_url(self, method, Params, ExpiresIn):
            calls.append((method, Params, ExpiresIn))
            return f"https://minio.example/presigned/{len(calls)}"

    class FakeSettings:
        minio_public_endpoint = "http://localhost:9000"

    monkeypatch.setattr(sm, "get_public_minio_client", lambda settings: FakeClient())
    sm._presign_cache.clear()
    try:
        u1 = sm.presign_material_get(
            FakeSettings(), "bkt", "k.pdf",
            filename="讲义.pdf", disposition="inline", expires=300,
        )
        u2 = sm.presign_material_get(
            FakeSettings(), "bkt", "k.pdf",
            filename="讲义.pdf", disposition="inline", expires=300,
        )
        assert u1 == u2 == "https://minio.example/presigned/1"
        assert len(calls) == 1  # 第二次命中缓存，没再签

        # 不同 disposition（下载）→ key 不同 → 重签
        u3 = sm.presign_material_get(
            FakeSettings(), "bkt", "k.pdf",
            filename="讲义.pdf", disposition="attachment", expires=60,
        )
        assert u3 == "https://minio.example/presigned/2"
        assert len(calls) == 2

        # 倒拨缓存时间戳到缓存窗口（expires*0.8）之外 → 重签
        ck = next(iter(sm._presign_cache))
        sm._presign_cache[ck] = (sm._presign_cache[ck][0], time.time() - 250, 300)
        u4 = sm.presign_material_get(
            FakeSettings(), "bkt", "k.pdf",
            filename="讲义.pdf", disposition="inline", expires=300,
        )
        assert u4 == "https://minio.example/presigned/3"
        assert len(calls) == 3
    finally:
        sm._presign_cache.clear()


def test_gate_lock_not_enrolled_403(tmp_path: Path, fake_s3):
    """Gate A 权限闸：非试看课时未开通 → 403（lock_reason=not_enrolled）。"""
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    bind_fake(app, fake_s3)
    _, _, course, _, lesson = build_lesson_without_content(app)
    block = create_materials_block(client, headers, lesson["id"])
    asset = seed_ready_asset(app, "讲义.pdf", content=PDF_CONTENT)
    _bind(app, client, headers, block["id"], asset["asset_id"])
    assert client.post(f"/api/admin/courses/{course['id']}/publish",
                       headers=headers).status_code == 200
    # 不设试看：open_policy 默认 closed → 未开通学生不可见

    stu = student_login(app)
    resp = stu.get(
        f"/api/lessons/{lesson['id']}/blocks/{block['id']}/materials/{asset['asset_id']}/download"
    )
    assert resp.status_code == 403


def test_gate_lock_sequential_403(tmp_path: Path, fake_s3):
    """Gate B 路径闸：前置必修块未完成 → 403（lock_reason=sequential）。"""
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    bind_fake(app, fake_s3)
    _, _, course, _, lesson = build_lesson_without_content(app)
    first = _create_block(client, headers, lesson["id"], unlock_rule="free", required=True)
    locked = _create_block(client, headers, lesson["id"], unlock_rule="sequential", required=True)
    first_asset = seed_ready_asset(app, "前置讲义.pdf", content=PDF_CONTENT)
    asset = seed_ready_asset(app, "讲义.pdf", content=PDF_CONTENT)
    _bind(app, client, headers, first["id"], first_asset["asset_id"])
    _bind(app, client, headers, locked["id"], asset["asset_id"])
    assert client.post(f"/api/admin/courses/{course['id']}/publish",
                       headers=headers).status_code == 200
    _set_trial_whole(app, lesson["id"])

    stu = student_login(app)
    # 权限闸过了（试看），但顺序闸拦住：前面的 first 还没完成
    resp = stu.get(
        f"/api/lessons/{lesson['id']}/blocks/{locked['id']}/materials/{asset['asset_id']}/download"
    )
    assert resp.status_code == 403


def test_not_ready_asset_404(tmp_path: Path, fake_s3):
    """MaterialAsset.status != ready → 404（与学生端清单过滤口径一致）。"""
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    bind_fake(app, fake_s3)
    asset = seed_ready_asset(app, "转码中.pdf", content=PDF_CONTENT)
    lesson, block = _ready_lesson(app, client, headers, asset_id=asset["asset_id"])

    db = app.state.session_factory()
    try:
        row = db.get(MaterialAsset, asset["asset_id"])
        row.status = "uploading"
        db.commit()
    finally:
        db.close()

    stu = student_login(app)
    resp = stu.get(
        f"/api/lessons/{lesson['id']}/blocks/{block['id']}/materials/{asset['asset_id']}/download"
    )
    assert resp.status_code == 404
