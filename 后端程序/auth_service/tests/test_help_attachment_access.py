"""附件下发与下架的范围闸。

这几条实现是对的，但**曾经一条用例都没有**：把学生侧的归属判断整段删掉，
附件测试仍然 4 条全绿——任何登录学生猜一个 id 就能读到别人的私聊图片，
而测试一声不吭。没红过的闸门等于不存在。
"""

import io

from PIL import Image
from test_exam import build_app, scsrf, student_login
from test_help_chat_lines_api import _admin_login, _seed_help_class


def _png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), (10, 120, 90)).save(buffer, format="PNG")
    return buffer.getvalue()


def _uploaded_attachment(app):
    """学生传一张图，返回 (学生客户端, 附件 id)。"""
    student = student_login(app, "learner")
    seeded = _seed_help_class(app)
    created = student.post(
        "/api/student/help-requests",
        headers={**scsrf(student), "Idempotency-Key": "access-seed"},
        json={"class_id": seeded["class_id"], "body": "带图", "context_type": "general"},
    )
    assert created.status_code == 201, created.text
    uploaded = student.post(
        f"/api/student/help-requests/{created.json()['id']}/attachments",
        headers={**scsrf(student), "Idempotency-Key": "access-att"},
        files={"file": ("a.png", io.BytesIO(_png()), "image/png")},
    )
    assert uploaded.status_code == 201, uploaded.text
    return student, uploaded.json()["id"]


def test_another_student_cannot_read_someone_elses_attachment(tmp_path):
    """私聊图片只有本人看得到；越界与不存在共用逐字相同的 404。"""
    app = build_app(tmp_path)
    owner, attachment_id = _uploaded_attachment(app)

    assert owner.get(f"/api/help-attachments/{attachment_id}").status_code == 200  # 哨兵

    intruder = student_login(app, "intruder")
    denied = intruder.get(f"/api/help-attachments/{attachment_id}")
    missing = intruder.get("/api/help-attachments/999999")
    assert denied.status_code == 404, denied.text
    # 逐字相同：否则「404 但文案不一样」照样能被用来枚举附件是否存在。
    assert denied.json() == missing.json()


def test_outsider_teacher_cannot_read_or_purge_the_attachment(tmp_path):
    """别班教师有 help_respond，但这条资源不在他的范围里 —— 范围闸 404。"""
    app = build_app(tmp_path)
    _owner, attachment_id = _uploaded_attachment(app)

    outsider, headers = _admin_login(app, "line-outsider")
    read = outsider.get(f"/api/help-attachments/{attachment_id}")
    assert read.status_code == 404, read.text
    purge = outsider.post(f"/api/admin/help-attachments/{attachment_id}/purge", headers=headers)
    assert purge.status_code == 404, purge.text

    # 哨兵：本班承办教师读得到、也下架得了，别把闸门拦过头。
    teacher, teacher_headers = _admin_login(app, "line-assignee")
    assert teacher.get(f"/api/help-attachments/{attachment_id}").status_code == 200
    assert teacher.post(
        f"/api/admin/help-attachments/{attachment_id}/purge", headers=teacher_headers
    ).status_code == 200


def test_purged_attachment_is_gone_for_everyone(tmp_path):
    """下架之后：对象没了、行还在、任何人再读都是 410 而不是裂图。"""
    app = build_app(tmp_path)
    owner, attachment_id = _uploaded_attachment(app)
    teacher, headers = _admin_login(app, "line-assignee")
    assert teacher.post(
        f"/api/admin/help-attachments/{attachment_id}/purge", headers=headers
    ).status_code == 200

    assert owner.get(f"/api/help-attachments/{attachment_id}").status_code == 410
    assert teacher.get(f"/api/help-attachments/{attachment_id}").status_code == 410


def test_a_role_without_help_respond_cannot_purge(tmp_path):
    """功能闸在范围闸之前：没有答疑能力的后台账号，连下架都不该走到范围判断。"""
    app = build_app(tmp_path)
    _owner, attachment_id = _uploaded_attachment(app)
    no_cap, headers = _admin_login(app, "line-no-cap")
    denied = no_cap.post(f"/api/admin/help-attachments/{attachment_id}/purge", headers=headers)
    assert denied.status_code == 403, denied.text


def test_a_row_marked_purged_is_refused_even_if_the_file_survives(tmp_path):
    """`purged_at` 本身就是拒绝依据，不能只靠「文件没了」兜底。

    正常下架会同时删文件，所以两道检查看起来等价——把 `purged_at` 那道拆掉，
    上面几条用例一条都不会红。但它们**不等价**：unlink 失败、或者将来有只标记
    不删文件的清理路径时，少了这道检查就会把已下架的内容照发出去。
    这条用例故意只标记、不删文件，把两者区分开。
    """
    from app.models import HelpMessageAttachment
    from app.routers.help_requests import _attachment_path
    from app.security import utcnow

    app = build_app(tmp_path)
    owner, attachment_id = _uploaded_attachment(app)

    db = app.state.session_factory()
    try:
        row = db.get(HelpMessageAttachment, attachment_id)
        row.purged_at = utcnow()
        db.commit()
        survivor = _attachment_path(app.state.settings, row)
    finally:
        db.close()
    assert survivor.is_file(), "本用例的前提就是文件还在，前提不成立就测不到东西"

    assert owner.get(f"/api/help-attachments/{attachment_id}").status_code == 410
