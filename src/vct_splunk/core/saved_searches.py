"""Saved-search dispatch. Click-free core.

Saved-search CRUD rides the generic :mod:`vct_splunk.core.resource` engine (see
the ``SAVED_SEARCH`` spec in :mod:`vct_splunk.commands.registry`); only dispatch
lives here, because running a saved search is an action, not CRUD. Saved
searches are **namespaced**: every call takes an explicit ``owner`` and ``app``
(the command layer resolves them via
:func:`vct_splunk.core.namespace.resolve_ns`, which keeps writes out of the
default ``search`` app).
"""

from __future__ import annotations

from typing import Any

from .client import SplunkClient
from .namespace import ns_path

_SUFFIX = "saved/searches"


def build_dispatch_payload(
    *,
    trigger_actions: bool = False,
    earliest: str | None = None,
    latest: str | None = None,
) -> dict[str, Any]:
    """Build the form body for dispatching a saved search.

    Split out of :func:`dispatch_saved_search` so both the real request and the
    ``--dry-run`` preview are built from the same code — the preview can never
    drift from what actually gets sent.
    """
    data: dict[str, Any] = {"trigger_actions": int(bool(trigger_actions))}
    if earliest is not None:
        data["dispatch.earliest_time"] = earliest
    if latest is not None:
        data["dispatch.latest_time"] = latest
    return data


def dispatch_saved_search(
    client: SplunkClient,
    name: str,
    *,
    owner: str,
    app: str,
    trigger_actions: bool = False,
    earliest: str | None = None,
    latest: str | None = None,
) -> dict[str, Any]:
    """Dispatch (run) a saved search and return the new job's SID.

    Dispatching creates a server-side job, like ``search run``; it is not a config
    change, so it uses the non-gated POST. The returned SID can be polled with
    ``search get``.
    """
    data = build_dispatch_payload(trigger_actions=trigger_actions, earliest=earliest, latest=latest)
    body = client.post(ns_path(f"{_SUFFIX}/{name}/dispatch", owner=owner, app=app), data)
    sid = body.get("sid") if isinstance(body, dict) else None
    if not sid and isinstance(body, dict):
        entries = body.get("entry") or []
        sid = entries[0].get("name") if entries else None
    return {"sid": sid, "dispatched": bool(sid)}
