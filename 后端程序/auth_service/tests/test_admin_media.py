"""题干配图上传。

盯住三件事：**只信解码结果**（改后缀塞进来的非图片必须拒）、**重编码剥 EXIF**
（手机拍的题目照片带 GPS，会一路走到学员端）、**按内容去重**（同一张图从不同设备
传来 EXIF 不同，对原始字节算哈希就去不掉重）。
"""

import os
from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image
from test_exam import admin_login, build_app

from app.models import MediaAsset


def build_media_app(tmp_path, **overrides):
    return build_app(tmp_path, media_upload_root=str(tmp_path / "media"), **overrides)


def png_bytes(size=(40, 30), color=(200, 30, 30)) -> bytes:
    with BytesIO() as stream:
        Image.new("RGB", size, color).save(stream, format="PNG")
        return stream.getvalue()


def jpeg_with_gps() -> bytes:
    """带 GPS 的 JPEG。Pillow 存 EXIF 要走 Exif 对象，手拼字节串会被解码器忽略。"""
    image = Image.new("RGB", (60, 40), (10, 120, 200))
    exif = Image.Exif()
    exif[0x8825] = {1: "N", 2: (39.0, 54.0, 0.0)}   # GPSInfo
    exif[0x010E] = "ImageDescription-SENTINEL"       # 一条普通 EXIF，一并验证被剥掉
    with BytesIO() as stream:
        image.save(stream, format="JPEG", exif=exif)
        return stream.getvalue()


def upload(client, headers, content: bytes, name="p.png", mime="image/png"):
    return client.post("/api/admin/media/images", headers=headers,
                       files={"file": (name, content, mime)})


def test_upload_returns_url_and_writes_file(tmp_path):
    app = build_media_app(tmp_path)
    client, headers = admin_login(app)

    response = upload(client, headers, png_bytes())
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["url"].startswith("/media/")
    assert (body["width"], body["height"]) == (40, 30)

    # URL 与磁盘路径必须是同一套：两级分桶目录 + sha256 文件名
    relative = body["url"].removeprefix("/media/")
    assert (tmp_path / "media" / relative).is_file()
    assert relative == f"{body['sha256'][:2]}/{body['sha256']}.png"

    db = app.state.session_factory()
    try:
        asset = db.get(MediaAsset, body["sha256"])
        assert asset is not None and asset.ext == "png"
    finally:
        db.close()


def test_same_image_is_stored_once(tmp_path):
    """一套模板图被 50 道题引用，磁盘上只该有一份。"""
    app = build_media_app(tmp_path)
    client, headers = admin_login(app)

    first = upload(client, headers, png_bytes()).json()
    second = upload(client, headers, png_bytes()).json()
    assert first["sha256"] == second["sha256"]
    assert len(list((tmp_path / "media").rglob("*.png"))) == 1


def test_exif_is_stripped(tmp_path):
    """重编码的主要目的。GPS 留在图里，等于把老师拍照的位置发给每一个考生。"""
    app = build_media_app(tmp_path)
    client, headers = admin_login(app)

    body = upload(client, headers, jpeg_with_gps(), name="photo.jpg", mime="image/jpeg").json()
    stored = tmp_path / "media" / body["url"].removeprefix("/media/")
    with Image.open(stored) as image:
        assert not dict(image.getexif())
    assert b"ImageDescription-SENTINEL" not in stored.read_bytes()


def test_disguised_file_is_rejected(tmp_path):
    """把 .exe 改名成 .png。这个目录要被浏览器当图片加载，只认解码结果。"""
    app = build_media_app(tmp_path)
    client, headers = admin_login(app)

    response = upload(client, headers, b"MZ\x90\x00 not an image at all")
    assert response.status_code == 400
    assert "无法识别" in response.json()["detail"]


def test_oversized_image_is_rejected(tmp_path):
    app = build_media_app(tmp_path, media_max_bytes=256 * 1024)
    client, headers = admin_login(app)

    # 随机噪声压不动，稳定超过 256KB（纯色图 PNG 能压到几百字节，测不出上限）
    noise = Image.frombytes("RGB", (700, 700), os.urandom(700 * 700 * 3))
    with BytesIO() as stream:
        noise.save(stream, format="PNG")
        response = upload(client, headers, stream.getvalue())
    assert response.status_code == 413


def test_large_image_is_downscaled(tmp_path):
    """4000×3000 的手机直出图在题干里没人要看原图，等比缩到上限即可。"""
    app = build_media_app(tmp_path, media_max_dimension=512)
    client, headers = admin_login(app)

    body = upload(client, headers, png_bytes(size=(1600, 800))).json()
    assert (body["width"], body["height"]) == (512, 256)


def test_upload_requires_csrf_header(tmp_path):
    app = build_media_app(tmp_path)
    client, _headers = admin_login(app)
    assert upload(client, {}, png_bytes()).status_code == 403


def test_upload_requires_login(tmp_path):
    """带着合法 CSRF 但没登录也不行——CSRF 防的是跨站，不是未授权。"""
    app = build_media_app(tmp_path)
    anonymous = TestClient(app)
    anonymous.get("/api/admin/csrf")
    response = upload(anonymous, {"X-CSRF-Token": anonymous.cookies.get("admin_csrf_token")},
                      png_bytes())
    assert response.status_code == 401
