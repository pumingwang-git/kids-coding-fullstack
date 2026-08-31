"""同屏答疑上下文的服务端规范化契约。"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType


CONTEXT_TYPE_ALIASES = MappingProxyType({
    "general": "general",
    "course": "course",
    "lesson": "lesson",
    "block": "lesson_block",
    "problem": "lesson_problem",
    "attempt": "attempt",
})
ATTEMPT_CONTEXT_SOURCES = frozenset({"lesson_attempt", "paper_attempt"})


@dataclass(frozen=True)
class NormalizedHelpContext:
    context_type: str
    context_source: str | None
    context_key: str


def _positive_id(value: int | None, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{field} must be a positive integer")
    return value


def _problem_number(value: str | None) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("problem_id_no is required")
    return value.strip()


def normalize_help_context(
    context_type: str,
    *,
    context_id: int | None = None,
    context_source: str | None = None,
    problem_id_no: str | None = None,
) -> NormalizedHelpContext:
    """Build the server-owned grouping key from an already-authorized context.

    ``problem_id_no`` must come from the resolved ``Problem`` row. Callers must
    never pass through a client-provided ``context_key`` or problem number.
    """

    canonical_type = CONTEXT_TYPE_ALIASES.get(context_type)
    if canonical_type is None:
        raise ValueError("unsupported help context type")

    if canonical_type == "general":
        if context_id is not None or context_source is not None or problem_id_no is not None:
            raise ValueError("general context does not accept identifiers")
        return NormalizedHelpContext("general", None, "general")

    if canonical_type == "lesson_problem":
        if context_source is not None:
            raise ValueError("problem context does not accept context_source")
        problem_number = _problem_number(problem_id_no)
        return NormalizedHelpContext(canonical_type, None, f"lesson_problem:{problem_number}")

    if canonical_type == "attempt":
        attempt_id = _positive_id(context_id, "context_id")
        if context_source not in ATTEMPT_CONTEXT_SOURCES:
            raise ValueError("attempt context_source is invalid")
        problem_number = _problem_number(problem_id_no)
        key = f"attempt:{context_source}:{attempt_id}:{problem_number}"
        return NormalizedHelpContext(canonical_type, context_source, key)

    if context_source is not None or problem_id_no is not None:
        raise ValueError(f"{context_type} context accepts only context_id")
    resolved_id = _positive_id(context_id, "context_id")
    return NormalizedHelpContext(canonical_type, None, f"{canonical_type}:{resolved_id}")
