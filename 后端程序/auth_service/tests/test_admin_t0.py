"""T0 的能力、菜单与字典协议守卫。"""
import re
from pathlib import Path

import pytest
from test_admin_auth import admin_client, admin_csrf_headers, admin_login
from test_admin_role_change import login_as, seed_admin

from app.audit_summary import EVENT_CATEGORY, event_type_options
from app.permissions import (
    ASSIGNABLE_ROLE_NAMES,
    CAPABILITY_CATALOG,
    KNOWN_ROLE_NAMES,
    ROLE_ALLOWED_PAGES,
    ROLE_CAPABILITIES,
    ROLE_MENUS,
)

ADMIN_DIR = Path(__file__).resolve().parents[3] / "前端程序" / "study-blog-vue" / "public" / "admin"


def test_role_capabilities_and_menus_cover_every_known_role():
    assert set(ROLE_CAPABILITIES) == set(KNOWN_ROLE_NAMES)
    assert set(ROLE_MENUS) == set(KNOWN_ROLE_NAMES)
    assert set(ROLE_ALLOWED_PAGES) == set(KNOWN_ROLE_NAMES)
    assert all(set(capabilities) == set(CAPABILITY_CATALOG) for capabilities in ROLE_CAPABILITIES.values())
    assert "admin" not in ASSIGNABLE_ROLE_NAMES


def test_scratch_review_capability_matches_the_real_teaching_roles():
    allowed = {
        role for role, capabilities in ROLE_CAPABILITIES.items()
        if capabilities["scratch_review"]
    }
    assert allowed == {"super_admin", "academic_admin", "teacher", "assistant"}


def test_dict_event_types_are_generated_from_event_category():
    options = event_type_options()
    assert {item["machine_name"] for item in options} == set(EVENT_CATEGORY)
    assert all(set(item) == {"machine_name", "display_name"} for item in options)


def test_layout_consumes_me_menus_and_has_no_super_only_patch():
    source = (ADMIN_DIR / "admin-layout.js").read_text(encoding="utf-8")
    assert "me.menus" in source
    assert "superOnly" not in source


def test_layout_displays_server_role_label_with_key_fallback():
    source = (ADMIN_DIR / "admin-layout.js").read_text(encoding="utf-8")
    assert "me.role_label || me.role" in source


def test_question_review_hint_describes_capability_not_fixed_roles_or_self_review():
    source = (ADMIN_DIR / "questions.html").read_text(encoding="utf-8")
    match = re.search(
        r"function reviewBlockedReason\(problem, allowed\) \{(?P<body>.*?)\n\s*\}",
        source,
        flags=re.S,
    )
    assert match
    body = match.group("body")
    assert "当前账号缺少内容审核权限" in body
    assert "reviewer" not in body and "super_admin" not in body
    assert "不可自审" not in body and "isAuthor" not in body


def test_me_and_dicts_expose_server_owned_protocol(tmp_path):
    with admin_client(tmp_path) as client:
        assert admin_login(client, admin_csrf_headers(client)).status_code == 200
        me = client.get("/api/admin/me").json()
        assert me["capabilities"]["export_class_insight"] is True
        assert "audit-logs.html" in me["menus"]
        assert "password-change.html" in me["allowed_pages"]
        dicts = client.get("/api/admin/dicts")
        assert dicts.status_code == 200
        payload = dicts.json()
        assert {item["machine_name"] for item in payload["event_types"]} == set(EVENT_CATEGORY)
        assert {item["role"] for item in payload["menus"]} == set(KNOWN_ROLE_NAMES)
        assert {item["key"] for item in payload["capabilities"]} == set(CAPABILITY_CATALOG)
        assert {item["value"] for item in payload["roles"]} == set(ASSIGNABLE_ROLE_NAMES)


@pytest.mark.parametrize("role", KNOWN_ROLE_NAMES)
def test_me_allowed_pages_match_the_server_role_protocol(tmp_path, role):
    with admin_client(tmp_path) as client:
        if role == "super_admin":
            assert admin_login(client, admin_csrf_headers(client)).status_code == 200
        else:
            seed_admin(client, f"pages-{role}", role)
            login_as(client, f"pages-{role}")

        response = client.get("/api/admin/me")
        assert response.status_code == 200, response.text
        assert response.json()["allowed_pages"] == list(ROLE_ALLOWED_PAGES[role])
