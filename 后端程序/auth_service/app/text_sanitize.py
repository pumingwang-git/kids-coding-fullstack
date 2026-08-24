from __future__ import annotations

import re


_TAG_RE = re.compile(r"<[^>]*>")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def plain_text(value: str) -> str:
    """Remove markup and control characters without HTML escaping."""

    return _CONTROL_RE.sub("", _TAG_RE.sub("", value or "")).strip()
