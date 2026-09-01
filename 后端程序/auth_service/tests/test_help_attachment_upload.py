"""答疑附件：真的传一次，并证明落盘的字节是我们自己编出来的。

现有 `tests/` 里只有附件的**迁移**与**契约**测试，没有一条真的传过文件——
上传路径整条没被执行过，第一次真实调用会怎样，测试说不出来。
"""

import io
from pathlib import Path

from PIL import Image
from test_exam import build_app, scsrf, student_login
from test_help_chat_lines_api import _seed_help_class

from app.models import HelpMessageAttachment


def _png(size=(8, 8), color=(200, 30, 30)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def _open_request(app):
    student = student_login(app, "learner")
    seeded = _seed_help_class(app)
    created = student.post(
        "/api/student/help-requests",
        headers={**scsrf(student), "Idempotency-Key": "attach-seed"},
        json={"class_id": seeded["class_id"], "body": "带附件", "context_type": "general"},
    )
    assert created.status_code == 201, created.text
    return student, created.json()["id"]


def _upload(app, student, request_id, *, raw, filename, content_type, key):
    return student.post(
        f"/api/student/help-requests/{request_id}/attachments",
        headers={**scsrf(student), "Idempotency-Key": key},
        files={"file": (filename, io.BytesIO(raw), content_type)},
    )


def test_student_can_actually_upload_an_image(tmp_path):
    """最基本的一条：上传一张合法图片要成功，并且文件真的落在盘上。"""
    app = build_app(tmp_path)
    student, request_id = _open_request(app)
    response = _upload(app, student, request_id, raw=_png(), filename="a.png",
                       content_type="image/png", key="attach-ok")
    assert response.status_code == 201, response.text

    db = app.state.session_factory()
    try:
        row = db.query(HelpMessageAttachment).one()
        stored = Path(app.state.settings.help_attachment_upload_root) / row.storage_key
        assert stored.is_file(), f"数据行写了，但盘上没有文件：{stored}"
    finally:
        db.close()


def test_uploaded_bytes_are_reencoded_not_stored_verbatim(tmp_path):
    """落盘的必须是我们自己编出来的字节，不是上传上来那份。

    判据用「PNG 尾部接一段垃圾数据」：合法图片解码后重编码，尾巴会被丢掉；
    原样落盘则会一字节不差地保留。**这条不写，消毒做没做从测试上看不出来。**
    """
    app = build_app(tmp_path)
    student, request_id = _open_request(app)
    polyglot = _png() + b"PK\x03\x04" + b"payload-that-must-not-survive" * 8
    response = _upload(app, student, request_id, raw=polyglot, filename="b.png",
                       content_type="image/png", key="attach-polyglot")
    assert response.status_code == 201, response.text

    db = app.state.session_factory()
    try:
        row = db.query(HelpMessageAttachment).one()
        stored = (Path(app.state.settings.help_attachment_upload_root) / row.storage_key).read_bytes()
    finally:
        db.close()
    assert b"payload-that-must-not-survive" not in stored, "尾部伪装数据原样落盘了：没有重编码"
    assert stored != polyglot, "落盘字节与上传字节完全相同：没有重编码"


def test_content_type_alone_does_not_get_a_file_in(tmp_path):
    """`Content-Type` 是客户端说了算的，不能当作判据。

    两条一起测：改了 MIME 的非图片要被拒；`image/svg+xml` 也要被拒——
    它能通过 `startswith("image/")`，而 SVG 是可执行 XML，会被 `<img>` 加载。
    """
    app = build_app(tmp_path)
    student, request_id = _open_request(app)

    disguised = _upload(app, student, request_id, raw=b"MZ\x90\x00 not an image at all",
                        filename="x.png", content_type="image/png", key="attach-disguised")
    assert disguised.status_code in (415, 422), f"改个 MIME 就混进来了：{disguised.status_code}"

    svg = _upload(app, student, request_id,
                  raw=b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
                  filename="x.svg", content_type="image/svg+xml", key="attach-svg")
    assert svg.status_code in (415, 422), f"SVG 被收下了：{svg.status_code}"


def test_private_attachment_can_be_read_by_owner_and_is_purged_on_recall(tmp_path):
    """真实走一遍下发与撤回：对象文件不是公开资源，也不能在撤回后继续读取。"""
    app = build_app(tmp_path)
    student, request_id = _open_request(app)
    uploaded = _upload(app, student, request_id, raw=_png(), filename="c.png",
                       content_type="image/png", key="attach-read")
    assert uploaded.status_code == 201, uploaded.text

    attachment_url = uploaded.json()["url"]
    readable = student.get(attachment_url)
    assert readable.status_code == 200, readable.text
    assert readable.headers["cache-control"] == "private, no-store"
    assert readable.headers["content-type"].startswith("image/webp")

    db = app.state.session_factory()
    try:
        attachment = db.query(HelpMessageAttachment).one()
        message_id = attachment.help_message_id
        stored = Path(app.state.settings.help_attachment_upload_root) / attachment.storage_key
        assert message_id is not None and stored.exists()
    finally:
        db.close()

    recalled = student.post(
        f"/api/student/help-messages/{message_id}/recall", headers=scsrf(student), json={}
    )
    assert recalled.status_code == 200, recalled.text
    assert recalled.json()["recalled"] is True
    assert recalled.json()["body"] == ""
    assert student.get(attachment_url).status_code == 410
    assert not stored.exists()
