"""审计日志页静态契约：枚举来自 dicts，且只读双主体展示。"""
import re
from pathlib import Path

ADMIN_DIR = Path(__file__).resolve().parents[3] / "前端程序" / "study-blog-vue" / "public" / "admin"


def read(name):
    return (ADMIN_DIR / name).read_text(encoding="utf-8")


def test_audit_page_exists_and_uses_registered_read_route():
    html, script = read("audit-logs.html"), read("audit-logs.js")
    assert 'id="auditRows"' in html
    assert 'adminRequest(`/audit/events?' in script
    assert 'adminRequest("/dicts")' in script


def test_audit_page_keeps_two_subject_columns_and_never_renders_ip_or_delete():
    html, script = read("audit-logs.html"), read("audit-logs.js")
    assert "操作人" in html and "涉及学员" in html
    assert "admin_user_id" in script and "user_id" in script
    body = re.sub(r"//.*$|/\*.*?\*/", "", html + script, flags=re.M | re.S)
    assert "ip_hmac" not in body and "删除" not in body and "delete" not in body.lower()


def test_audit_filters_render_event_and_outcome_options_from_dicts():
    script = read("audit-logs.js")
    assert "dicts.event_types" in script and "dicts.outcomes" in script
    assert "item.event_type" in script and "item.outcome" in script
    assert not re.search(r"(?:event_type|outcome)\s*[:=]\s*\[[^]]*['\"]", script)
