"""Scratch 审核/删除/撤回对齐回归（2026-08-15 SC-123 反馈）：
approve 落审核人、reject 必填原因、published 可删（未引用）、unpublish 撤回 version+1。
"""
import tempfile
from pathlib import Path

from test_exam import admin_login, build_app
from test_scratch import sb3_bytes
from test_scratch_admin_flow import _create, _upload_starter


def _setup():
    app = build_app(Path(tempfile.mkdtemp()))
    client, headers = admin_login(app)
    cid = _create(client, headers)["id"]
    _upload_starter(client, headers, cid, sb3_bytes())
    return client, headers, cid


def test_approve_records_reviewer():
    client, headers, cid = _setup()
    assert client.post(f"/api/admin/scratch/challenges/{cid}/submit", headers=headers, json={}).status_code == 200
    r = client.post(f"/api/admin/scratch/challenges/{cid}/approve", headers=headers, json={})
    assert r.status_code == 200, r.text
    body = r.json()["challenge"]
    assert body["status"] == "published"
    assert body["reviewed_by"] is not None, "approve 应落审核人"


def test_reject_requires_reason_and_persists():
    client, headers, cid = _setup()
    assert client.post(f"/api/admin/scratch/challenges/{cid}/submit", headers=headers, json={}).status_code == 200
    # 无原因 → 422
    assert client.post(f"/api/admin/scratch/challenges/{cid}/reject", headers=headers, json={}).status_code == 422
    # 带原因 → 落库
    r = client.post(f"/api/admin/scratch/challenges/{cid}/reject", headers=headers, json={"reason": "规则不完整"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "draft"
    assert body["rejection"]["reason"] == "规则不完整", body


def test_unpublish_turns_draft_and_bumps_version():
    client, headers, cid = _setup()
    assert client.post(f"/api/admin/scratch/challenges/{cid}/submit", headers=headers, json={}).status_code == 200
    assert client.post(f"/api/admin/scratch/challenges/{cid}/approve", headers=headers, json={}).status_code == 200
    r = client.post(f"/api/admin/scratch/challenges/{cid}/unpublish", headers=headers, json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "draft" and body["version"] == 2, body


def test_published_unreferenced_challenge_can_delete():
    client, headers, cid = _setup()
    assert client.post(f"/api/admin/scratch/challenges/{cid}/submit", headers=headers, json={}).status_code == 200
    assert client.post(f"/api/admin/scratch/challenges/{cid}/approve", headers=headers, json={}).status_code == 200
    # 未绑定课时、无学生提交 → 可删（与题目 approved 删除同口径）
    assert client.delete(f"/api/admin/scratch/challenges/{cid}", headers=headers).status_code == 204


def test_pending_challenge_cannot_delete():
    client, headers, cid = _setup()
    assert client.post(f"/api/admin/scratch/challenges/{cid}/submit", headers=headers, json={}).status_code == 200
    r = client.delete(f"/api/admin/scratch/challenges/{cid}", headers=headers)
    assert r.status_code == 409, r.text
