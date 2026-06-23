"""Backend capability map and selection. Click-free core.

The CLI targets two backends: Splunk Enterprise (splunkd REST, the default and
the certified path) and Splunk Cloud (ACS, read-only and not yet certified). This
module reports which resource classes each backend supports so a caller can ask
"what can I do here?" without trial and error -- unsupported operations are named
explicitly rather than failing through to an unofficial endpoint.
"""

from __future__ import annotations

import os
from typing import Any

#: What each backend supports. Values are either True (full support) or a short
#: string describing the limit (read-only, not supported, and why).
CAPABILITIES: dict[str, dict[str, Any]] = {
    "enterprise": {
        "search": True,
        "indexes": True,
        "saved_searches": True,
        "knowledge_objects": True,
        "users_and_roles": True,
        "inputs_and_outputs": True,
        "kvstore": True,
        "apps": True,
        "health": True,
    },
    "cloud": {
        "indexes": "read-only (ACS)",
        "hec_tokens": "read-only (ACS)",
        "roles": "read-only (ACS)",
        "search": "not supported via ACS (run against the search head directly)",
        "knowledge_objects": "not supported via ACS",
        "writes": "not supported this release (read-only)",
    },
}

_DEFAULT = "enterprise"


def active_backend(backend: str | None = None) -> str:
    """Resolve the active backend: the argument, else ``$SPLUNK_BACKEND``, else enterprise."""
    chosen = (backend or os.environ.get("SPLUNK_BACKEND") or _DEFAULT).strip().lower()
    return chosen if chosen in CAPABILITIES else _DEFAULT


def inspect_backend(backend: str | None = None) -> dict[str, Any]:
    """Report the active backend and the operations it supports."""
    resolved = active_backend(backend)
    report: dict[str, Any] = {"backend": resolved, "capabilities": CAPABILITIES[resolved]}
    if resolved == "cloud":
        report["note"] = (
            "Cloud/ACS coverage is read-only and not yet certified against a live stack; "
            "confidence is capped until a real canary exists."
        )
    return report
