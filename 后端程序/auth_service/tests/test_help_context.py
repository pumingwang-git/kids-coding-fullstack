from types import SimpleNamespace

import pytest

from app.help_authorization import (
    can_approve_support_content,
    can_request_support_content,
    can_respond_to_help,
    can_start_realtime_assist,
)
from app.help_context import normalize_help_context


@pytest.mark.parametrize(
    ("context_type", "context_id", "expected_type", "expected_key"),
    (
        ("course", 3, "course", "course:3"),
        ("lesson", 5, "lesson", "lesson:5"),
        ("block", 7, "lesson_block", "lesson_block:7"),
    ),
)
def test_context_ids_are_normalized_by_the_server(
    context_type, context_id, expected_type, expected_key
):
    context = normalize_help_context(context_type, context_id=context_id)
    assert context.context_type == expected_type
    assert context.context_source is None
    assert context.context_key == expected_key


def test_problem_key_uses_public_problem_number_not_database_id():
    context = normalize_help_context(
        "problem", context_id=999, problem_id_no="HELP-PY-001"
    )
    assert context.context_key == "lesson_problem:HELP-PY-001"
    assert "999" not in context.context_key


@pytest.mark.parametrize("source", ("lesson_attempt", "paper_attempt"))
def test_attempt_key_keeps_source_attempt_and_problem_identity(source):
    context = normalize_help_context(
        "attempt", context_id=11, context_source=source, problem_id_no="PY-7"
    )
    assert context.context_key == f"attempt:{source}:11:PY-7"


@pytest.mark.parametrize(
    "kwargs",
    (
        {"context_type": "general", "context_id": 1},
        {"context_type": "course", "context_id": 0},
        {"context_type": "problem", "context_id": 1},
        {"context_type": "attempt", "context_id": 1, "problem_id_no": "P-1"},
        {
            "context_type": "attempt",
            "context_id": 1,
            "context_source": "lesson_attempt",
        },
    ),
)
def test_incomplete_or_ambiguous_context_is_rejected(kwargs):
    with pytest.raises(ValueError):
        normalize_help_context(**kwargs)


@pytest.mark.parametrize(
    ("role", "respond", "realtime", "request_content", "approve_content"),
    (
        ("teacher", True, True, False, False),
        ("assistant", True, True, False, False),
        ("academic_admin", False, False, True, False),
        # super_admin 拿到 help_respond / realtime_assist 不是疏漏：
        # `SUPER_ROLE: _capabilities(*CAPABILITY_CATALOG)`（permissions.py:125，HEAD 既有）
        # 决定了往目录里加任何能力，超管都会自动获得；`test_admin_t0.py:26` 守着这条。
        # 《58》§5.1「超管默认只看统计与元数据」**不能靠抽掉能力兑现**，
        # 要由 H1 的「内容查看申请 + 审批 + 审计」兑现（本阶段不做）。
        # ⚠️ 在 H1 落地之前，超管读答疑正文没有留痕——这是已知且被接受的临时状态。
        ("super_admin", True, True, True, True),
        ("editor", False, False, False, False),
    ),
)
def test_help_capability_matrix(
    role, respond, realtime, request_content, approve_content
):
    admin = SimpleNamespace(role=role)
    assert can_respond_to_help(admin) is respond
    assert can_start_realtime_assist(admin) is realtime
    assert can_request_support_content(admin) is request_content
    assert can_approve_support_content(admin) is approve_content
