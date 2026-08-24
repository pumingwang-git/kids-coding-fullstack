from pathlib import Path

ROOT = Path(__file__).resolve().parents[3] / "前端程序" / "study-blog-vue" / "public" / "admin"


def test_notification_page_escapes_server_text_and_has_no_inline_style():
    html = (ROOT / "notifications.html").read_text(encoding="utf-8")
    script = (ROOT / "notifications.js").read_text(encoding="utf-8")
    assert 'style="' not in html
    assert "${escapeHtml(item.title || \"\")}" in script
    assert "${escapeHtml(item.body)}" in script


def test_shared_admin_topbar_links_to_notifications():
    layout = (ROOT / "admin-layout.js").read_text(encoding="utf-8")
    assert 'href="notifications.html"' in layout
    assert 'aria-label="通知"' in layout
    assert 'id="adminNotificationCount"' in layout
    assert 'adminRequest("/notifications/unread-count")' in layout
