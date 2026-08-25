"""T0 的能力、菜单与字典协议守卫。"""
from pathlib import Path

from app.audit_summary import EVENT_CATEGORY, event_type_options
from app.permissions import KNOWN_ROLE_NAMES, ROLE_CAPABILITIES, ROLE_MENUS
from test_admin_auth import admin_client, admin_csrf_headers, admin_login

ADMIN_DIR = Path(__file__).resolve().parents[3] / "前端程序" / "study-blog-vue" / "public" / "admin"


def test_role_capabilities_and_menus_cover_every_known_role():
    assert set(ROLE_CAPABILITIES) == set(KNOWN_ROLE_NAMES)
    assert set(ROLE_MENUS) == set(KNOWN_ROLE_NAMES)
    assert all("export_class_insight" in ROLE_CAPABILITIES[role] for role in KNOWN_ROLE_NAMES)


def test_dict_event_types_are_generated_from_event_category():
    options = event_type_options()
    assert {item["machine_name"] for item in options} == set(EVENT_CATEGORY)
    assert all(set(item) == {"machine_name", "display_name"} for item in options)


def test_layout_consumes_me_menus_and_has_no_super_only_patch():
    source = (ADMIN_DIR / "admin-layout.js").read_text(encoding="utf-8")
    assert "me.menus" in source
    assert "superOnly" not in source


def test_me_and_dicts_expose_server_owned_protocol(tmp_path):
    with admin_client(tmp_path) as client:
        assert admin_login(client, admin_csrf_headers(client)).status_code == 200
        me = client.get("/api/admin/me").json()
        assert me["capabilities"]["export_class_insight"] is True
        assert "audit-logs.html" in me["menus"]
        dicts = client.get("/api/admin/dicts")
        assert dicts.status_code == 200
        payload = dicts.json()
        assert {item["machine_name"] for item in payload["event_types"]} == set(EVENT_CATEGORY)
        assert {item["role"] for item in payload["menus"]} == set(KNOWN_ROLE_NAMES)
