"""Stable versions for server-owned reporting metric definitions.

Keep the current value here so every learning-report endpoint and export uses
the same provenance marker.  Increment it only when the underlying metric
definitions change; a deployment or code refactor alone is not a new metric
version.
"""

METRIC_VERSION = "v1"

__all__ = ["METRIC_VERSION"]
