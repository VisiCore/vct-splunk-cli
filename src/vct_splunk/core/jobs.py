"""Search job lifecycle over ``/services/search/jobs``. Click-free core.

Jobs are addressed by their SID, not by a namespace. ``list`` and ``get`` are
reads; ``cancel`` is a mutation and goes through the client's gated ``write``.
"""

from __future__ import annotations

from typing import Any

from .client import SplunkClient
from .errors import NotFoundError
from .search import JOBS_PATH


def list_jobs(client: SplunkClient) -> list[dict[str, Any]]:
    """List search jobs (every dispatched job visible to the caller)."""
    return [_job(e) for e in client.get_collection(JOBS_PATH)]


def get_job(client: SplunkClient, sid: str) -> dict[str, Any]:
    """Show one search job by SID.

    Raises:
        NotFoundError: If no job has that SID.
    """
    entries = client.get(f"{JOBS_PATH}/{sid}").get("entry") or []
    if not entries:
        raise NotFoundError(f"Search job {sid!r} not found.")
    return _job(entries[0])


def cancel_job(client: SplunkClient, sid: str) -> dict[str, Any]:
    """Cancel a search job (frees its resources on the server).

    A POST to the job's ``control`` endpoint with ``action=cancel``. Routed
    through the client's ``write`` so ``--dry-run`` previews it and sends nothing.
    """
    return client.write("POST", f"{JOBS_PATH}/{sid}/control", {"action": "cancel"})


def _job(entry: dict[str, Any]) -> dict[str, Any]:
    """Normalize a Splunk job entry to a flat, stable shape.

    The SID is the entry name; the owner and app live in the ``acl`` block, not
    in ``content``.
    """
    content = entry.get("content") or {}
    acl = entry.get("acl") or {}
    return {
        "sid": entry.get("name"),
        "dispatch_state": content.get("dispatchState"),
        "done_progress": content.get("doneProgress"),
        "event_count": content.get("eventCount"),
        "result_count": content.get("resultCount"),
        "is_done": content.get("isDone"),
        "is_failed": content.get("isFailed"),
        "run_duration": content.get("runDuration"),
        "owner": acl.get("owner"),
        "app": acl.get("app"),
        "search": content.get("search"),
    }
