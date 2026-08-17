"""学生个人资料（文档 28 P2）：资料读取、签名更新、头像上传的最小回归。"""
from io import BytesIO
from pathlib import Path

from PIL import Image

from test_exam import build_app, scsrf, student_login

STUDENT_PASSWORD = "A-long-password-123!"


def _png_bytes(color: tuple = (120, 180, 240), size: tuple = (64, 64)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def test_profile_defaults_and_signature_update(tmp_path: Path):
    app = build_app(tmp_path)
    client = student_login(app, username="profilelearner")

    profile = client.get("/api/student/profile")
    assert profile.status_code == 200, profile.text
    body = profile.json()
    assert body["user"]["username"] == "profilelearner"
    assert body["user"]["status"] == "active"
    assert body["avatar_url"] == ""
    assert body["learning_signature"] == ""
    assert body["overview"]["total"] == 0
    assert body["overview"]["due"] == 0
    assert body["overview"]["total_answered"] == 0

    updated = client.patch("/api/student/profile", headers=scsrf(client),
                           json={"learning_signature": "今天也要加油呀"})
    assert updated.status_code == 200, updated.text
    assert updated.json()["learning_signature"] == "今天也要加油呀"

    again = client.get("/api/student/profile").json()
    assert again["learning_signature"] == "今天也要加油呀"

    # 超长签名被 pydantic 拦下（文档 28：80 字以内）
    too_long = client.patch("/api/student/profile", headers=scsrf(client),
                            json={"learning_signature": "好" * 81})
    assert too_long.status_code == 422


def test_avatar_upload_validates_and_persists(tmp_path: Path):
    app = build_app(tmp_path, avatar_upload_root=str(tmp_path / "avatars"))
    client = student_login(app, username="avatarname")

    bad = client.post("/api/student/profile/avatar", headers=scsrf(client),
                      files={"file": ("avatar.txt", b"not an image", "text/plain")})
    assert bad.status_code == 400

    good = client.post("/api/student/profile/avatar", headers=scsrf(client),
                       files={"file": ("avatar.png", _png_bytes(), "image/png")})
    assert good.status_code == 201, good.text
    url = good.json()["avatar_url"]
    assert url.startswith("/avatars/")
    # 文件确实落盘：/avatars/{sha[:2]}/{sha}.{ext}
    relative = url.removeprefix("/avatars/")
    assert (Path(str(tmp_path / "avatars")) / relative).exists()

    # 替换头像后 URL 更新，且 /me 同步带回（顶部头像依赖它）
    other = client.post("/api/student/profile/avatar", headers=scsrf(client),
                        files={"file": ("avatar2.png", _png_bytes((40, 90, 160)), "image/png")})
    assert other.status_code == 201
    assert other.json()["avatar_url"] != url

    me = client.get("/api/auth/me").json()
    assert me["avatar_url"] == other.json()["avatar_url"]


def test_profile_is_private_to_current_student(tmp_path: Path):
    app = build_app(tmp_path)
    owner = student_login(app, username="ownername")
    owner.patch("/api/student/profile", headers=scsrf(owner),
                json={"learning_signature": "只属于我"})

    stranger = student_login(app, username="strangername")
    body = stranger.get("/api/student/profile").json()
    assert body["learning_signature"] == ""
    assert body["user"]["username"] == "strangername"
