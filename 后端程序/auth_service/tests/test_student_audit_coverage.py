"""E7 补账：学生端两处此前 0 审计的动作。

《55》§8 裁定——
- 改资料 / 换头像 → `profile_update`，归 `authz`（5 年）；摘要只记变更字段的 old/new，
  **不记头像二进制、不记邮箱**；
- 作品分享到广场 → `work_share`，归 `collab`（2 年）；摘要记 id 与可见范围，
  **不记作品内容**。

这两条与 T1 同性质：今天没记的，明年出纠纷时永远拿不回来。
"""

import json
from io import BytesIO
from pathlib import Path

from PIL import Image
from sqlalchemy import select

from app.audit_summary import EVENT_CATEGORY, RETENTION_DAYS
from app.models import AuditEvent
from test_exam import build_app, scsrf, student_login
from test_scratch import (
    build_scratch_lesson,
    sb3_bytes,
    scratch_env,
    scripted_sprite,
    stage_target,
)


def _events(app, event_type: str) -> list[AuditEvent]:
    db = app.state.session_factory()
    try:
        return list(db.scalars(
            select(AuditEvent).where(AuditEvent.event_type == event_type).order_by(AuditEvent.id)
        ))
    finally:
        db.close()


def _png_bytes(color: tuple = (10, 200, 90), size: tuple = (48, 48)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def test_student_events_are_registered_with_the_decided_retention():
    """归类必须与《55》§8 的裁定一致，且不带 admin_ 前缀（学生端库值）。"""
    assert EVENT_CATEGORY["profile_update"] == "authz"
    assert RETENTION_DAYS["authz"] == 5 * 365
    assert EVENT_CATEGORY["work_share"] == "collab"
    assert RETENTION_DAYS["collab"] == 2 * 365
    assert "admin_profile_update" not in EVENT_CATEGORY
    assert "admin_work_share" not in EVENT_CATEGORY


def test_signature_update_is_audited_with_old_and_new(tmp_path: Path):
    app = build_app(tmp_path)
    client = student_login(app, username="auditlearner")

    assert client.patch("/api/student/profile", headers=scsrf(client),
                        json={"learning_signature": "第一版"}).status_code == 200
    assert client.patch("/api/student/profile", headers=scsrf(client),
                        json={"learning_signature": "第二版"}).status_code == 200

    rows = _events(app, "profile_update")
    assert len(rows) == 2
    changed = json.loads(rows[-1].summary_json)["changed"]
    assert changed["learning_signature"] == {"old": "第一版", "new": "第二版"}, \
        "改名属身份类变更，必须能回答「从什么改成了什么」"
    assert rows[-1].resource_type == "student_profile"


def test_avatar_upload_is_audited_without_leaking_binary(tmp_path: Path):
    app = build_app(tmp_path)
    client = student_login(app, username="avatarlearner")

    raw = _png_bytes()
    resp = client.post("/api/student/profile/avatar", headers=scsrf(client),
                       files={"file": ("a.png", raw, "image/png")})
    assert resp.status_code == 201, resp.text

    rows = _events(app, "profile_update")
    assert len(rows) == 1
    summary = rows[0].summary_json
    changed = json.loads(summary)["changed"]
    assert changed["avatar_url"]["old"] in ("", None)
    assert changed["avatar_url"]["new"].startswith("/avatars/")
    # 脱敏哨兵：摘要里不得出现图片字节
    assert "\\x89PNG" not in summary and raw[:8].hex() not in summary


def test_work_share_is_audited_without_leaking_content(tmp_path: Path):
    app = scratch_env(tmp_path)
    sclient = student_login(app)
    built = build_scratch_lesson(app)
    ctx = sclient.get(f"/api/scratch/lesson-blocks/{built['block_ids'][0]}").json()
    project_id = ctx["project"]["id"]
    assert sclient.put(
        f"/api/scratch/projects/{project_id}", headers=scsrf(sclient),
        files={"file": ("p.sb3", sb3_bytes([stage_target(), scripted_sprite(name="猫")]),
                        "application/zip")},
        data={"source": "manual", "challenge_id": str(ctx["challenge"]["id"])},
    ).status_code == 200

    shared = sclient.post("/api/scratch/works/share", headers=scsrf(sclient),
                          json={"project_id": project_id})
    assert shared.status_code == 200, shared.text

    rows = _events(app, "work_share")
    assert len(rows) == 1
    summary = json.loads(rows[0].summary_json)
    assert summary["work_id"] == shared.json()["id"]
    assert summary["is_public"] is True, "可见范围是追责时的关键字段"
    # 脱敏哨兵：摘要不得携带作品内容寻址信息
    assert "sb3_key" not in rows[0].summary_json and "sha256" not in rows[0].summary_json

    # 哨兵（别记过头）：幂等重复分享没有新发布任何东西，不得再写一条。
    again = sclient.post("/api/scratch/works/share", headers=scsrf(sclient),
                         json={"project_id": project_id})
    assert again.status_code == 200 and again.json()["already_shared"] is True
    assert len(_events(app, "work_share")) == 1, "幂等返回不是一次新的对外发布"
