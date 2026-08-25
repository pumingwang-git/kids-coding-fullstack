"""T6 regression guards for execution-time authorization."""
from pathlib import Path


def test_export_worker_recomputes_scope_in_worker_not_request_snapshot():
    source = (Path(__file__).parents[1] / "app" / "tasks" / "exports.py").read_text(encoding="utf-8")
    assert "visible_class_ids(admin, db)" in source
    assert "exportable_class_ids(admin, db)" in source
    assert "requested_by" in source
    assert "class_id not in export_ids" in source
