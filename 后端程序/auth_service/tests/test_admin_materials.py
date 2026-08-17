"""资料管理与 Windows 文件夹迁移：文件夹 / 检索 / 上传 / 绑定 / 迁移会话全链路。

对应交接文档《12、资料管理与Windows文件夹迁移》§9 实施顺序 1～5 与 §10 验收清单：
- 文件夹按需展开、深层目录面包屑、循环/同名/非空删除防护；
- 检索分页可与类型/标签/目录组合，page_size 受限；
- 上传完成前不标 ready：sha256 由后台任务从对象存储计算（前端只信服务端结果）；
- 课时块绑定幂等、解绑不删源文件、删除被引用资料被拒并返回引用清单；
- 迁移会话：清单分批（非法路径拒绝）、分片续传、finalize 建目录、冲突三策略
  （skip/rename/version）都有明确结果。

测试环境没有 MinIO：monkeypatch app.s3_multipart.get_minio_client 为 FakeS3Client
（内存对象存储）。TestClient 会在响应后同步执行 background task（starlette 行为），
因此 complete/finalize 后立即 GET 即可看到终态。
"""
import hashlib
import io
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_admin_course_content import build_lesson_without_content
from test_exam import admin_login, build_app

from app.models import MaterialAsset, MaterialAssetTag, MaterialFolder, MaterialTag

# ==================== Fake S3 ====================


class FakeS3Client:
    """内存对象存储：普通对象 + multipart 上传，接口形状对齐 boto3 S3 client。"""

    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self.multiparts: dict[str, dict] = {}
        self.part_data: dict[tuple[str, int], bytes] = {}
        self._seq = 0

    def put_object(self, Bucket, Key, Body: bytes):
        self.objects[Key] = Body
        return {"ETag": '"fake"', "ContentLength": len(Body)}

    def generate_presigned_url(self, method, Params, ExpiresIn=3600):
        if method == "put_object":
            return f"http://fake-put/{Params['Key']}"
        return f"http://fake-part/{Params['UploadId']}/{Params['PartNumber']}"

    def create_multipart_upload(self, Bucket, Key, ContentType):
        self._seq += 1
        uid = f"fake-mp-{self._seq}"
        self.multiparts[uid] = {"bucket": Bucket, "key": Key, "parts": {}}
        return {"UploadId": uid}

    def upload_part(self, upload_id: str, part_number: int, data: bytes):
        """模拟浏览器 PUT 一片。"""
        self.part_data[(upload_id, part_number)] = data
        self.multiparts[upload_id]["parts"][part_number] = '"fake-etag"'

    def list_parts(self, Bucket, Key, UploadId, PartNumberMarker=0, **kwargs):
        parts = self.multiparts[UploadId]["parts"]
        return {
            "Parts": [
                {"PartNumber": n, "ETag": e}
                for n, e in sorted(parts.items()) if n > PartNumberMarker
            ],
            "IsTruncated": False,
        }

    def complete_multipart_upload(self, Bucket, Key, UploadId, MultipartUpload):
        data = b"".join(
            self.part_data[(UploadId, p["PartNumber"])]
            for p in sorted(MultipartUpload["Parts"], key=lambda x: x["PartNumber"])
        )
        self.objects[Key] = data
        self.multiparts.pop(UploadId, None)

    def abort_multipart_upload(self, Bucket, Key, UploadId):
        self.multiparts.pop(UploadId, None)

    def head_object(self, Bucket, Key):
        if Key not in self.objects:
            raise KeyError(f"object not found: {Key}")
        return {"ContentLength": len(self.objects[Key])}

    def get_object(self, Bucket, Key, Range=None):
        """带 Range 支持，形状对齐 S3：206 时回 ContentRange（bytes start-end/total）。

        真实 S3 对合法 Range 一定返回 ContentRange，且 end 是**本次实际给到的最后
        一个字节**（open-ended `bytes=start-` 时就是 total-1）。资料代理的
        Content-Range 直接透传它，所以这里必须照实模拟，否则测不出越界回归。
        """
        if Key not in self.objects:
            raise KeyError(f"object not found: {Key}")
        data = self.objects[Key]
        if Range is None:
            return {"Body": io.BytesIO(data), "ContentLength": len(data), "ETag": '"fake"'}
        match = re.match(r"bytes=(\d*)-(\d*)$", Range)
        if not match:
            raise ValueError(f"unsupported range: {Range}")
        start_s, end_s = match.groups()
        start = int(start_s) if start_s else 0
        end = int(end_s) if end_s else len(data) - 1
        end = min(end, len(data) - 1)
        chunk = data[start : end + 1]
        return {
            "Body": io.BytesIO(chunk),
            "ContentLength": len(chunk),
            "ContentRange": f"bytes {start}-{end}/{len(data)}",
            "ETag": '"fake"',
        }

    def delete_object(self, Bucket, Key):
        self.objects.pop(Key, None)


@pytest.fixture
def fake_s3(monkeypatch):
    fake = FakeS3Client()
    monkeypatch.setattr("app.s3_multipart.get_minio_client", lambda settings: fake)
    return fake


def bind_fake(app, fake):
    """把 fixture 的 FakeS3 挂到 app 上，seed 辅助据此填对象。"""
    app.state._fake_s3 = fake


# ==================== 造数据辅助 ====================


def seed_folder(app, name: str, parent_id: int | None = None) -> int:
    db = app.state.session_factory()
    try:
        folder = MaterialFolder(name=name, parent_id=parent_id)
        db.add(folder)
        db.commit()
        return folder.id
    finally:
        db.close()


def seed_ready_asset(app, display_name: str, folder_id: int | None = None,
                     content: bytes = b"hello", status: str = "ready",
                     sha256: str | None = None, tags: list[str] | None = None) -> dict:
    """直接落库一个资产行；status=ready 时同步把对象放进 FakeS3（下载/校验用）。"""
    db = app.state.session_factory()
    try:
        key = f"materials/seed/{display_name}"
        fake = getattr(app.state, "_fake_s3", None)
        if fake is not None and status == "ready":
            fake.objects[key] = content
        asset = MaterialAsset(
            folder_id=folder_id, display_name=display_name, object_key=key,
            mime_type="application/pdf", asset_type="document",
            size_bytes=len(content), sha256=sha256 or hashlib.sha256(content).hexdigest(),
            status=status,
        )
        db.add(asset)
        db.flush()
        for tag_name in tags or []:
            tag = db.scalar(select(MaterialTag).where(MaterialTag.name == tag_name))
            if tag is None:
                tag = MaterialTag(name=tag_name)
                db.add(tag)
                db.flush()
            db.add(MaterialAssetTag(asset_id=asset.id, tag_id=tag.id))
        db.commit()
        return {"asset_id": asset.id, "object_key": key}
    finally:
        db.close()


def create_materials_block(client, headers, lesson_id: int) -> dict:
    resp = client.post(
        f"/api/admin/lessons/{lesson_id}/blocks", headers=headers,
        json={"block_type": "materials", "title": "阅读资料"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ==================== 文件夹 ====================


def test_folders_tree_breadcrumb_and_guards(tmp_path: Path, fake_s3):
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    bind_fake(app, fake_s3)

    root = client.post("/api/admin/material-folders", headers=headers,
                       json={"name": "数学"}).json()
    assert root["child_count"] == 0
    # 同级重名 409
    assert client.post("/api/admin/material-folders", headers=headers,
                       json={"name": "数学"}).status_code == 409
    child = client.post("/api/admin/material-folders", headers=headers,
                        json={"name": "七年级", "parent_id": root["id"]}).json()

    # 循环防护：把 root 移进自己的子目录 → 400
    assert client.patch(f"/api/admin/material-folders/{root['id']}", headers=headers,
                        json={"parent_id": child["id"]}).status_code == 400

    # 按需展开：根列表只带直接子项计数
    data = client.get("/api/admin/material-folders").json()
    assert data["parent_id"] is None
    assert [f["name"] for f in data["items"]] == ["数学"]
    assert data["items"][0]["child_count"] == 1
    sub = client.get("/api/admin/material-folders", params={"parent_id": root["id"]}).json()
    assert [f["name"] for f in sub["items"]] == ["七年级"]

    # 重命名 + 移动 + 面包屑
    renamed = client.patch(f"/api/admin/material-folders/{child['id']}", headers=headers,
                           json={"name": "八年级"}).json()
    assert renamed["name"] == "八年级"
    moved = client.patch(f"/api/admin/material-folders/{child['id']}", headers=headers,
                         json={"parent_id": None}).json()
    assert moved["parent_id"] is None
    detail = client.get(f"/api/admin/material-folders/{child['id']}").json()
    assert [p["name"] for p in detail["path"]] == ["八年级"]

    # 非空删除 409（root 下仍有子目录？不：child 已移到根。先移回来再验非空删除）
    client.patch(f"/api/admin/material-folders/{child['id']}", headers=headers,
                 json={"parent_id": root["id"]})
    assert client.delete(f"/api/admin/material-folders/{root['id']}", headers=headers).status_code == 409
    assert client.delete(f"/api/admin/material-folders/{child['id']}", headers=headers).status_code == 200
    assert client.delete(f"/api/admin/material-folders/{root['id']}", headers=headers).status_code == 200


# ==================== 检索 ====================


def test_materials_search_filter_and_pagination(tmp_path: Path, fake_s3):
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    bind_fake(app, fake_s3)
    folder = client.post("/api/admin/material-folders", headers=headers,
                         json={"name": "课件"}).json()
    a = seed_ready_asset(app, "第一章讲义.pdf", folder_id=folder["id"], tags=["重点"])
    seed_ready_asset(app, "练习答案.docx", tags=["作业"])
    seed_ready_asset(app, "第二章讲义.pdf", folder_id=folder["id"], tags=["重点"])

    assert client.get("/api/admin/materials").json()["total"] == 3
    data = client.get("/api/admin/materials", params={"keyword": "讲义"}).json()
    assert data["total"] == 2
    # folder 过滤 + 未分类
    assert client.get("/api/admin/materials", params={"folder_id": folder["id"]}).json()["total"] == 2
    assert client.get("/api/admin/materials", params={"folder_id": -1}).json()["total"] == 1
    # type + tag 组合（本测试内第一个标签 id=1）
    assert client.get("/api/admin/materials", params={"type": "document", "tag": "1"}).json()["total"] == 2
    item = client.get(f"/api/admin/materials/{a['asset_id']}").json()
    assert item["tags"] == ["重点"] and item["asset_type"] == "document"
    # page_size 限制：非法值回落默认
    assert client.get("/api/admin/materials", params={"page_size": 999}).json()["page_size"] == 50


# ==================== 普通上传 ====================


def test_upload_small_presigned_put_flow(tmp_path: Path, fake_s3):
    """小文件：presigned PUT → complete（head 核对）→ 后台算 sha256 → ready。"""
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    bind_fake(app, fake_s3)
    init = client.post("/api/admin/materials/uploads/init", headers=headers,
                       json={"display_name": "说明.pdf", "file_size": 5}).json()
    assert init["mode"] == "presigned_put" and init["presigned_url"]
    key = init["presigned_url"].split("http://fake-put/", 1)[-1]
    fake_s3.put_object(Bucket="materials", Key=key, Body=b"hello")  # 模拟浏览器 PUT

    resp = client.post(f"/api/admin/materials/uploads/{init['upload_session_id']}/complete",
                       headers=headers, json={"parts": []})
    assert resp.status_code == 200 and resp.json()["status"] == "uploading"

    detail = client.get(f"/api/admin/materials/{init['asset_id']}").json()
    assert detail["status"] == "ready"
    assert detail["sha256"] is not None

    dl = client.get(f"/api/admin/materials/{init['asset_id']}/download")
    assert dl.status_code == 200 and dl.content == b"hello"


def test_upload_multipart_flow(tmp_path: Path, fake_s3):
    """大文件：multipart init → 逐片预签名 → complete 核对 parts → ready。"""
    app = build_app(tmp_path, material_part_size=5 * 1024 * 1024)
    client, headers = admin_login(app)
    bind_fake(app, fake_s3)
    file_size = 11 * 1024 * 1024
    init = client.post("/api/admin/materials/uploads/init", headers=headers,
                       json={"display_name": "大文件.zip", "file_size": file_size}).json()
    assert init["mode"] == "multipart" and init["part_count"] == 3

    upload_id = None
    parts = []
    remaining = file_size
    for n in range(1, 4):
        resp = client.get(f"/api/admin/materials/uploads/{init['upload_session_id']}/parts/{n}")
        assert resp.status_code == 200
        url = resp.json()["url"]
        upload_id = url.split("/")[-2]  # http://fake-part/{upload_id}/{n}
        chunk = min(5 * 1024 * 1024, remaining)
        remaining -= chunk
        fake_s3.upload_part(upload_id, n, b"x" * chunk)
        parts.append({"part_number": n, "etag": '"fake-etag"'})

    resp = client.post(f"/api/admin/materials/uploads/{init['upload_session_id']}/complete",
                       headers=headers, json={"parts": parts})
    assert resp.status_code == 200
    detail = client.get(f"/api/admin/materials/{init['asset_id']}").json()
    assert detail["status"] == "ready"
    assert detail["size_bytes"] == file_size


def test_upload_abort_marks_failed(tmp_path: Path, fake_s3):
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    bind_fake(app, fake_s3)
    init = client.post("/api/admin/materials/uploads/init", headers=headers,
                       json={"display_name": "半途而废.png", "file_size": 10}).json()
    resp = client.post(f"/api/admin/materials/uploads/{init['upload_session_id']}/abort",
                       headers=headers)
    assert resp.json()["status"] == "failed"
    assert client.get(f"/api/admin/materials/{init['asset_id']}").json()["status"] == "failed"


# ==================== 课时块绑定 ====================


def test_block_binding_and_delete_protection(tmp_path: Path, fake_s3):
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    bind_fake(app, fake_s3)
    _, _, _, _, lesson = build_lesson_without_content(app)
    block = create_materials_block(client, headers, lesson["id"])

    a = seed_ready_asset(app, "讲义A.pdf")
    b = seed_ready_asset(app, "讲义B.pdf")

    # 绑定（幂等：重复提交不重复）
    assert client.post(f"/api/admin/lesson-blocks/{block['id']}/materials", headers=headers,
                       json={"material_ids": [a["asset_id"], b["asset_id"]]}).status_code == 201
    assert client.post(f"/api/admin/lesson-blocks/{block['id']}/materials", headers=headers,
                       json={"material_ids": [a["asset_id"]]}).status_code == 201
    items = client.get(f"/api/admin/lesson-blocks/{block['id']}/materials").json()["items"]
    assert [i["material_id"] for i in items] == [a["asset_id"], b["asset_id"]]
    assert [i["sort_order"] for i in items] == [0, 1]

    # 块序列化带材料摘要
    blocks = client.get(f"/api/admin/lessons/{lesson['id']}/blocks").json()["blocks"]
    assert [m["material_id"] for m in blocks[0]["materials"]] == [a["asset_id"], b["asset_id"]]

    # 被引用资料删除 → 409 + 引用清单
    resp = client.delete(f"/api/admin/materials/{a['asset_id']}", headers=headers)
    assert resp.status_code == 409
    refs = resp.json()["detail"]["references"]
    assert refs[0]["block_id"] == block["id"]

    # 解绑不删源文件 → 解绑后可删，且对象回收
    assert client.delete(f"/api/admin/lesson-blocks/{block['id']}/materials/{a['asset_id']}",
                         headers=headers).status_code == 200
    assert client.delete(f"/api/admin/materials/{a['asset_id']}", headers=headers).status_code == 200
    assert fake_s3.objects.get("materials/seed/讲义A.pdf") is None

    # 删除块 → 级联解绑，源文件保留
    assert client.delete(f"/api/admin/lesson-blocks/{block['id']}", headers=headers).status_code == 200
    assert client.get(f"/api/admin/materials/{b['asset_id']}").json()["status"] == "ready"


def test_bind_requires_ready_material(tmp_path: Path, fake_s3):
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    bind_fake(app, fake_s3)
    _, _, _, _, lesson = build_lesson_without_content(app)
    block = create_materials_block(client, headers, lesson["id"])
    pending = seed_ready_asset(app, "未完成.pdf", status="uploading", sha256=None)
    resp = client.post(f"/api/admin/lesson-blocks/{block['id']}/materials", headers=headers,
                       json={"material_ids": [pending["asset_id"]]})
    assert resp.status_code == 400


# ==================== 迁移会话 ====================


def _start_import(client, headers, target_folder_id=None, policy="skip", preserve=True) -> dict:
    resp = client.post("/api/admin/material-imports", headers=headers, json={
        "source_root_name": "C:\\资料库",
        "target_folder_id": target_folder_id,
        "preserve_structure": preserve,
        "conflict_policy": policy,
    })
    assert resp.status_code == 201, resp.text
    return resp.json()


def _submit_manifest(client, headers, session_id, items):
    return client.post(f"/api/admin/material-imports/{session_id}/manifest-batches",
                       headers=headers, json={"items": items})


def _upload_and_complete_item(app, client, headers, session_id, item_id, content: bytes):
    """取上传参数 → 模拟直传（小文件 PUT / 大文件 multipart）→ complete。"""
    resp = client.post(f"/api/admin/material-imports/{session_id}/upload-parts",
                       headers=headers, json={"item_ids": [item_id]})
    assert resp.status_code == 200, resp.text
    item = resp.json()["items"][0]
    fake = getattr(app.state, "_fake_s3")
    parts = []
    if item["mode"] == "presigned_put":
        key = item["presigned_url"].split("http://fake-put/", 1)[-1]
        fake.objects[key] = content
    else:
        upload_id = item["upload_id"]
        part_size = item["part_size"]
        for n in range(1, item["part_count"] + 1):
            start = (n - 1) * part_size
            fake.upload_part(upload_id, n, content[start:start + part_size])
            parts.append({"part_number": n, "etag": '"fake-etag"'})
    resp = client.post(f"/api/admin/material-imports/{session_id}/items/{item_id}/complete",
                       headers=headers, json={"parts": parts})
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_import_full_flow_with_structure(tmp_path: Path, fake_s3):
    """完整链路：建会话 → 分批清单 → 上传 → finalize → 目录结构与资产落库。"""
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    bind_fake(app, fake_s3)
    session = _start_import(client, headers)

    batch = _submit_manifest(client, headers, session["id"], [
        {"client_id": "f1", "relative_path": "第一章/讲义.pdf", "file_name": "讲义.pdf",
         "size_bytes": 5},
        {"client_id": "f2", "relative_path": "第一章/作业.docx", "file_name": "作业.docx",
         "size_bytes": 5},
        {"client_id": "bad1", "relative_path": "../evil.exe", "file_name": "evil.exe",
         "size_bytes": 7},
    ]).json()
    assert batch["accepted"] == 2
    assert any(r["client_id"] == "bad1" for r in batch["rejected"])

    items = client.get(f"/api/admin/material-imports/{session['id']}").json()["items"]
    assert {i["client_id"] for i in items} == {"f1", "f2"}

    for item in items:
        _upload_and_complete_item(app, client, headers, session["id"], item["id"],
                                  content=b"abcde")  # 与 size_bytes=5 对齐

    assert client.post(f"/api/admin/material-imports/{session['id']}/finalize",
                       headers=headers).json()["status"] == "finalizing"
    data = client.get(f"/api/admin/material-imports/{session['id']}").json()
    assert data["status"] == "completed"
    assert data["summary"]["success"] == 2

    # 保留目录结构：目标下建了「第一章」
    folders = client.get("/api/admin/material-folders").json()["items"]
    assert [f["name"] for f in folders] == ["第一章"]
    assert folders[0]["asset_count"] == 2
    # 资产可检索、可下载
    materials = client.get("/api/admin/materials").json()["items"]
    assert len(materials) == 2 and all(m["status"] == "ready" for m in materials)


def test_import_conflict_policies(tmp_path: Path, fake_s3):
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    bind_fake(app, fake_s3)
    target = client.post("/api/admin/material-folders", headers=headers,
                         json={"name": "目标"}).json()
    seed_ready_asset(app, "同名.txt", folder_id=target["id"], content=b"AAA")

    def run_import(policy, entries) -> dict:
        session = _start_import(client, headers, target_folder_id=target["id"], policy=policy)
        resp = _submit_manifest(client, headers, session["id"], entries)
        assert resp.status_code == 200, resp.text
        for item in client.get(f"/api/admin/material-imports/{session['id']}").json()["items"]:
            _upload_and_complete_item(app, client, headers, session["id"], item["id"],
                                      content=entries_by_id[item["client_id"]])
        assert client.post(f"/api/admin/material-imports/{session['id']}/finalize",
                           headers=headers).status_code == 200
        return client.get(f"/api/admin/material-imports/{session['id']}").json()["summary"]

    # skip：同名跳过
    entries_by_id = {"a": b"AAA"}
    summary = run_import("skip", [{"client_id": "a", "relative_path": "同名.txt",
                                   "file_name": "同名.txt", "size_bytes": 3}])
    assert summary == {"total": 1, "success": 0, "skipped": 1, "conflicted": 0,
                       "failed": 0, "pending": 0}

    # rename：同名自动改名保留两份
    entries_by_id = {"b": b"BBB"}
    summary = run_import("rename", [{"client_id": "b", "relative_path": "同名.txt",
                                     "file_name": "同名.txt", "size_bytes": 3}])
    assert summary["conflicted"] == 1
    names = [a["display_name"] for a in client.get("/api/admin/materials",
             params={"folder_id": target["id"]}).json()["items"]]
    assert "同名.txt" in names and "同名 (2).txt" in names

    # version：同哈希跳过、不同哈希建新版本
    entries_by_id = {"c": b"AAA", "d": b"CCC"}
    summary = run_import("version", [
        {"client_id": "c", "relative_path": "同名.txt", "file_name": "同名.txt", "size_bytes": 3},
        {"client_id": "d", "relative_path": "同名.txt", "file_name": "同名.txt", "size_bytes": 3},
    ])
    assert summary["skipped"] == 1 and summary["conflicted"] == 1


def test_import_resume_reports_uploaded_parts(tmp_path: Path, fake_s3):
    """断点续传：上传中条目在 GET 恢复时返回已传分片（§5 第 7 条）。"""
    app = build_app(tmp_path, material_part_size=5 * 1024 * 1024)
    client, headers = admin_login(app)
    bind_fake(app, fake_s3)
    session = _start_import(client, headers)
    _submit_manifest(client, headers, session["id"], [
        {"client_id": "big", "relative_path": "大文件.dat", "file_name": "大文件.dat",
         "size_bytes": 11 * 1024 * 1024},
    ])
    item = client.get(f"/api/admin/material-imports/{session['id']}").json()["items"][0]
    resp = client.post(f"/api/admin/material-imports/{session['id']}/upload-parts",
                       headers=headers, json={"item_ids": [item["id"]]})
    assert resp.status_code == 200
    up = resp.json()["items"][0]
    fake_s3.upload_part(up["upload_id"], 1, b"x" * (5 * 1024 * 1024))  # 只传了第 1 片

    data = client.get(f"/api/admin/material-imports/{session['id']}",
                      params={"include_parts": 1}).json()
    assert data["items"][0]["uploaded_parts"] == [1]
    assert data["stats"]["uploading"] == 1


def test_import_cancel_then_finalize_rejected(tmp_path: Path, fake_s3):
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    bind_fake(app, fake_s3)
    session = _start_import(client, headers)
    assert client.post(f"/api/admin/material-imports/{session['id']}/cancel",
                       headers=headers).json()["status"] == "cancelled"
    assert client.post(f"/api/admin/material-imports/{session['id']}/finalize",
                       headers=headers).status_code == 409


def test_auth_and_stats(tmp_path: Path, fake_s3):
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    bind_fake(app, fake_s3)
    # 未登录 401
    assert TestClient(app).get("/api/admin/materials").status_code == 401
    # 统计
    folder = seed_folder(app, "统计目录")
    seed_ready_asset(app, "a.pdf", folder_id=folder, content=b"aaaa")
    seed_ready_asset(app, "b.pdf", content=b"bbbb")
    data = client.get("/api/admin/material-stats").json()
    assert data["total_assets"] == 2
    assert data["total_folders"] == 1
    assert data["total_bytes"] == 8
    assert data["month_new"] >= 0


# ==================== 评审修复回归（P0/P1） ====================


def test_publish_requires_materials_bound(tmp_path: Path, fake_s3):
    """P0-1 修复：materials 块不再被发布校验误当练习/作业要求试卷。"""
    from test_admin_course_content import _publish_problems, build_lesson_without_content

    app = build_app(tmp_path)
    client, headers = admin_login(app)
    bind_fake(app, fake_s3)
    _, _, course, _, lesson = build_lesson_without_content(app)
    block = create_materials_block(client, headers, lesson["id"])

    # 空资料块：发布被拦，错误码是 materials_empty（不再是 paper_missing_detail）
    problems = _publish_problems(client, headers, course["id"])
    assert any(p["code"] == "materials_empty" and p["block_id"] == block["id"] for p in problems)
    assert not any(p["code"] == "paper_missing_detail" for p in problems)

    # 绑定 ready 资料后可发布
    asset = seed_ready_asset(app, "讲义.pdf")
    client.post(f"/api/admin/lesson-blocks/{block['id']}/materials", headers=headers,
                json={"material_ids": [asset["asset_id"]]})
    assert client.post(f"/api/admin/courses/{course['id']}/publish",
                       headers=headers).status_code == 200


def test_student_sees_materials_blocks(tmp_path: Path, fake_s3):
    """P0-2 修复：学生端 DTO 下发阅读资料摘要，且不泄露 object_key。"""
    from test_admin_course_content import build_lesson_without_content
    from test_exam import student_login

    from app.models import CourseLesson

    app = build_app(tmp_path)
    client, headers = admin_login(app)
    bind_fake(app, fake_s3)
    _, _, course, _, lesson = build_lesson_without_content(app)
    block = create_materials_block(client, headers, lesson["id"])
    asset = seed_ready_asset(app, "讲义.pdf", content=b"abcde")
    client.post(f"/api/admin/lesson-blocks/{block['id']}/materials", headers=headers,
                json={"material_ids": [asset["asset_id"]]})
    assert client.post(f"/api/admin/courses/{course['id']}/publish", headers=headers).status_code == 200

    # 设为试看课时，学生无需开通即可解锁（enrollments 未落地前 deny by default）
    db = app.state.session_factory()
    try:
        row = db.get(CourseLesson, lesson["id"])
        row.is_trial = True
        row.open_policy = "whole"  # 开放策略是门控来源；is_trial 仅兼容同步
        db.commit()
    finally:
        db.close()

    stu = student_login(app)
    data = stu.get(f"/api/lessons/{lesson['id']}").json()
    assert data["unlocked"] is True
    materials_block = next(b for b in data["blocks"] if b["block_type"] == "materials")
    assert materials_block["materials"][0]["display_name"] == "讲义.pdf"
    assert materials_block["materials"][0]["asset_type"] == "document"
    assert "object_key" not in materials_block["materials"][0]


def test_import_session_owner_only(tmp_path: Path, fake_s3):
    """P0-3 修复：非创建者读清单 / 签发分片 / 完成上传一律 403。"""
    from app.models import AdminUser
    from app.security import password_hash

    app = build_app(tmp_path)
    client, headers = admin_login(app)
    bind_fake(app, fake_s3)
    session = _start_import(client, headers)
    _submit_manifest(client, headers, session["id"], [
        {"client_id": "x", "relative_path": "a.txt", "file_name": "a.txt", "size_bytes": 10},
    ])
    item = client.get(f"/api/admin/material-imports/{session['id']}").json()["items"][0]

    # 第二个管理员（editor）
    db = app.state.session_factory()
    try:
        db.add(AdminUser(username="other", password_hash=password_hash.hash("Other-pass-123!"),
                         display_name="other", role="editor"))
        db.commit()
    finally:
        db.close()
    other = TestClient(app)
    other.get("/api/admin/csrf")
    oh = {"X-CSRF-Token": other.cookies.get("admin_csrf_token")}
    assert other.post("/api/admin/login", headers=oh,
                      json={"username": "other", "password": "Other-pass-123!"}).status_code == 200
    oh = {"X-CSRF-Token": other.cookies.get("admin_csrf_token")}

    # 读会话 / 签发分片 / 完成上传全部 403
    assert other.get(f"/api/admin/material-imports/{session['id']}").status_code == 403
    assert other.get(f"/api/admin/material-imports/{session['id']}/items/{item['id']}/part-url",
                     params={"part_number": 1}).status_code == 403
    assert other.post(f"/api/admin/material-imports/{session['id']}/items/{item['id']}/complete",
                      headers=oh, json={"parts": []}).status_code == 403
    # 创建者仍可读
    assert client.get(f"/api/admin/material-imports/{session['id']}").status_code == 200


def test_sweep_resumes_stuck_tasks(tmp_path: Path, fake_s3):
    """P1 修复：启动扫尾恢复卡住的 sha256 校验与 finalize（后台任务不跨进程）。"""
    from app.models import MaterialAsset, MaterialImportItem, MaterialImportSession, MaterialUpload
    from app.routers.admin_material_imports import sweep_material_imports
    from app.routers.admin_materials import sweep_material_uploads

    app = build_app(tmp_path)
    client, headers = admin_login(app)
    bind_fake(app, fake_s3)

    # 造一个"上传会话已 complete、资产仍 uploading"的卡住记录
    db = app.state.session_factory()
    try:
        asset = MaterialAsset(display_name="卡住的资料.pdf", object_key="materials/sweep/a.pdf",
                              size_bytes=3, status="uploading")
        db.add(asset)
        db.flush()
        db.add(MaterialUpload(asset_id=asset.id, bucket="materials", object_key="materials/sweep/a.pdf",
                              upload_mode="presigned_put", file_size=3, status="completed"))
        db.commit()
        stuck_asset_id = asset.id

        # 造一个 finalizing 会话 + uploaded 条目
        session = MaterialImportSession(source_root_name="S", status="finalizing")
        db.add(session)
        db.flush()
        db.add(MaterialImportItem(session_id=session.id, client_id="f1", relative_path="a.txt",
                                  file_name="a.txt", size_bytes=3, status="uploaded",
                                  bucket="materials", object_key="materials/sweep/f1.txt"))
        db.commit()
        stuck_session_id = session.id
    finally:
        db.close()
    fake_s3.objects["materials/sweep/a.pdf"] = b"abc"
    fake_s3.objects["materials/sweep/f1.txt"] = b"abc"

    # 扫尾：sha256 校验恢复 → ready；finalize 恢复 → completed
    assert sweep_material_uploads(app.state.settings, app.state.session_factory) == 1
    assert sweep_material_imports(app.state.settings, app.state.session_factory) == 1

    db = app.state.session_factory()
    try:
        assert db.get(MaterialAsset, stuck_asset_id).status == "ready"
        assert db.get(MaterialAsset, stuck_asset_id).sha256 is not None
        assert db.get(MaterialImportSession, stuck_session_id).status == "completed"
    finally:
        db.close()
