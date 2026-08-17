"""课包封面上传（独立存储区域）。

与题干配图上传共用解码/重编码逻辑，但要盯住一件事：**存储区域必须独立**——
落盘根目录是 course_covers 而非 media，URL 前缀是 /course-covers/ 而非 /media/，
登记表是 course_covers 而非 media_assets。两个区域一旦混用，清理脚本就会
互相扫到对方的引用列，把正在用的图删掉。
"""

from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image
from test_exam import admin_login, build_app

from app.models import CourseCover, MediaAsset


def build_cover_app(tmp_path, **overrides):
    return build_app(
        tmp_path,
        media_upload_root=str(tmp_path / "media"),
        course_cover_upload_root=str(tmp_path / "course_covers"),
        **overrides,
    )


def png_bytes(size=(40, 30), color=(200, 30, 30)) -> bytes:
    with BytesIO() as stream:
        Image.new("RGB", size, color).save(stream, format="PNG")
        return stream.getvalue()


def upload(client, headers, content: bytes, name="cover.png", mime="image/png"):
    return client.post("/api/admin/course-covers", headers=headers,
                       files={"file": (name, content, mime)})


def test_cover_upload_uses_its_own_storage_area(tmp_path):
    """URL 前缀、落盘根目录、登记表必须与题干配图完全分开。"""
    app = build_cover_app(tmp_path)
    client, headers = admin_login(app)

    response = upload(client, headers, png_bytes())
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["url"].startswith("/course-covers/")
    assert (body["width"], body["height"]) == (40, 30)

    relative = body["url"].removeprefix("/course-covers/")
    # 封面落到 course_covers 目录，且 media 目录里什么都没有
    assert (tmp_path / "course_covers" / relative).is_file()
    assert not (tmp_path / "media").exists() or not list((tmp_path / "media").rglob("*"))

    db = app.state.session_factory()
    try:
        cover = db.get(CourseCover, body["sha256"])
        assert cover is not None and cover.ext == "png"
        assert db.get(MediaAsset, body["sha256"]) is None  # 不能串进题干配图表
    finally:
        db.close()


def test_cover_upload_does_not_pollute_problem_media(tmp_path):
    """同一张图分别走两个上传口，落两个不同的区域、登记两张表。"""
    app = build_cover_app(tmp_path)
    client, headers = admin_login(app)
    raw = png_bytes()

    cover = upload(client, headers, raw).json()
    problem = client.post("/api/admin/media/images", headers=headers,
                          files={"file": ("p.png", raw, "image/png")}).json()

    assert cover["sha256"] == problem["sha256"]
    assert cover["url"].startswith("/course-covers/")
    assert problem["url"].startswith("/media/")
    assert len(list((tmp_path / "course_covers").rglob("*.png"))) == 1
    assert len(list((tmp_path / "media").rglob("*.png"))) == 1


def test_cover_upload_is_content_addressed_and_deduped(tmp_path):
    app = build_cover_app(tmp_path)
    client, headers = admin_login(app)

    first = upload(client, headers, png_bytes()).json()
    second = upload(client, headers, png_bytes()).json()
    assert first["sha256"] == second["sha256"]
    assert len(list((tmp_path / "course_covers").rglob("*.png"))) == 1


def test_disguised_file_is_rejected(tmp_path):
    """把 .exe 改名成 .png。封面目录也要被浏览器当图片加载，只认解码结果。"""
    app = build_cover_app(tmp_path)
    client, headers = admin_login(app)

    response = upload(client, headers, b"MZ\x90\x00 not an image at all")
    assert response.status_code == 400
    assert "无法识别" in response.json()["detail"]


def test_oversized_cover_is_rejected(tmp_path):
    app = build_cover_app(tmp_path, media_max_bytes=256 * 1024)
    client, headers = admin_login(app)

    # 随机噪声压不动，稳定超过 256KB（纯色图 PNG 能压到几百字节，测不出上限）
    import os
    noise = Image.frombytes("RGB", (700, 700), os.urandom(700 * 700 * 3))
    with BytesIO() as stream:
        noise.save(stream, format="PNG")
        response = upload(client, headers, stream.getvalue())
    assert response.status_code == 413


def test_cover_upload_requires_csrf_and_login(tmp_path):
    app = build_cover_app(tmp_path)
    client, _headers = admin_login(app)

    assert upload(client, {}, png_bytes()).status_code == 403

    anonymous = TestClient(app)
    anonymous.get("/api/admin/csrf")
    response = upload(anonymous, {"X-CSRF-Token": anonymous.cookies.get("admin_csrf_token")},
                      png_bytes())
    assert response.status_code == 401
