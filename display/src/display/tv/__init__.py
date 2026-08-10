"""The television boundary.

**Only the interface is exported here.** The concrete `SamsungTv` is imported by
name, from the one place that builds it, so that importing `display.tv` does not
drag the `samsungtvws` fork in behind it. That keeps the seam honest in a way a
convenience re-export would quietly undo: everything above this line is written
against `TvClient` and can be exercised without a television or its library.
"""

from display.tv.client import (
    UPLOADED_CATEGORY,
    RemovalOutcome,
    SelectionAnnouncement,
    SelectionObserver,
    TvClient,
    TvRemovalUnconfirmed,
    TvUnavailable,
    TvUploadFailed,
)

__all__ = [
    "UPLOADED_CATEGORY",
    "RemovalOutcome",
    "SelectionAnnouncement",
    "SelectionObserver",
    "TvClient",
    "TvRemovalUnconfirmed",
    "TvUnavailable",
    "TvUploadFailed",
]
