from __future__ import annotations

from pathlib import Path

from app.permissions import ROLE_LABELS, SCOPE_LABELS
from app.student_tasks import EXAM_PHASE_LABELS, HOMEWORK_PHASE_LABELS, PRACTICE_PHASE_LABELS


ROOT = Path(__file__).resolve().parents[3]
ADMIN = ROOT / "前端程序" / "study-blog-vue" / "public" / "admin"
FILES = [ADMIN / "teaching.html", *ADMIN.glob("teaching*.js")]


def test_teaching_page_does_not_embed_backend_labels():
    assert FILES
    assert all(path.exists() for path in FILES)
    source = "\n".join(path.read_text(encoding="utf-8") for path in FILES)
    labels = (
        *HOMEWORK_PHASE_LABELS.values(),
        *PRACTICE_PHASE_LABELS.values(),
        *EXAM_PHASE_LABELS.values(),
        *SCOPE_LABELS.values(),
        *ROLE_LABELS.values(),
    )
    for label in labels:
        assert label not in source


def test_teaching_page_has_no_inline_style_and_menu_entry_exists():
    page = ADMIN / "teaching.html"
    assert page.exists()
    assert 'style="' not in page.read_text(encoding="utf-8")
    layout = ADMIN / "admin-layout.js"
    assert layout.exists()
    assert "teaching.html" in layout.read_text(encoding="utf-8")
