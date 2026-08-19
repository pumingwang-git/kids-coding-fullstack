"""考试名单页不得在前端维护目标类型文案。"""

from pathlib import Path

from app.routers.admin_papers import ASSIGNMENT_TARGET_LABELS


ADMIN_DIR = Path(__file__).resolve().parents[3] / "前端程序" / "study-blog-vue" / "public" / "admin"


def test_papers_page_does_not_hardcode_assignment_target_labels():
    source = "\n".join(
        (ADMIN_DIR / name).read_text(encoding="utf-8")
        for name in ("papers.js", "papers.html")
    )
    for label in ASSIGNMENT_TARGET_LABELS.values():
        assert label not in source, f"考试名单文案 {label} 被硬编码进前端"


def test_papers_page_renders_assignment_label_from_api_and_has_no_inline_styles():
    papers_js = (ADMIN_DIR / "papers.js").read_text(encoding="utf-8")
    papers_html = (ADMIN_DIR / "papers.html").read_text(encoding="utf-8")
    assert "item.target_type_label" in papers_js
    assert "target_type_options" in papers_js
    assert 'style="' not in papers_html


def test_papers_page_assignment_controls_and_css_are_present():
    papers_js = (ADMIN_DIR / "papers.js").read_text(encoding="utf-8")
    papers_html = (ADMIN_DIR / "papers.html").read_text(encoding="utf-8")
    css = (ADMIN_DIR / "admin.css").read_text(encoding="utf-8")
    assert 'id="assignmentMask"' in papers_html
    assert "data-assignments" in papers_js
    assert "data-end-assignment" in papers_js
    assert ".assignment-modal" in css
    assert css.count("{") == css.count("}")
