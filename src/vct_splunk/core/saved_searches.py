"""Saved-search CRUD + dispatch. Click-free core.

Saved searches are **namespaced**: every call takes an explicit ``owner`` and
``app`` (the command layer resolves them via
:func:`vct_splunk.core.namespace.resolve_ns`, which keeps writes out of the
default ``search`` app). The shape mirrors :mod:`vct_splunk.core.indexes`; it is
hand-written here rather than factored into a registry because saved searches are
only the second CRUD-shaped resource — the factory arrives once a third lands.
"""

from __future__ import annotations

from typing import Any

from .client import SplunkClient
from .errors import NotFoundError
from .namespace import ns_path

_SUFFIX = "saved/searches"


def list_saved_searches(client: SplunkClient, *, owner: str, app: str) -> list[dict[str, Any]]:
    """List saved searches in the given namespace (``-`` wildcards span all)."""
    return [_saved(e) for e in client.get_collection(ns_path(_SUFFIX, owner=owner, app=app))]


def get_saved_search(client: SplunkClient, name: str, *, owner: str, app: str) -> dict[str, Any]:
    """Show one saved search.

    Raises:
        NotFoundError: If no saved search by that name is visible in the namespace.
    """
    entries = client.get(ns_path(f"{_SUFFIX}/{name}", owner=owner, app=app)).get("entry") or []
    if not entries:
        raise NotFoundError(f"Saved search {name!r} not found.")
    return _saved(entries[0])


def create_saved_search(
    client: SplunkClient,
    name: str,
    *,
    owner: str,
    app: str,
    search: str,
    description: str | None = None,
    cron: str | None = None,
    is_scheduled: bool | None = None,
) -> dict[str, Any]:
    """Create a saved search in ``app`` (POST to the namespaced collection)."""
    data: dict[str, Any] = {"name": name, "search": search}
    _apply_optional(data, description=description, cron=cron, is_scheduled=is_scheduled)
    return _unwrap(client.write("POST", ns_path(_SUFFIX, owner=owner, app=app), data))


def update_saved_search(
    client: SplunkClient,
    name: str,
    *,
    owner: str,
    app: str,
    search: str | None = None,
    description: str | None = None,
    cron: str | None = None,
    is_scheduled: bool | None = None,
) -> dict[str, Any]:
    """Update a saved search in place.

    Splunk's POST to the object merges server-side, so only the fields passed
    here are sent. ``name`` is in the URL, never the body (renames are not done).
    """
    data: dict[str, Any] = {}
    if search is not None:
        data["search"] = search
    _apply_optional(data, description=description, cron=cron, is_scheduled=is_scheduled)
    return _unwrap(client.write("POST", ns_path(f"{_SUFFIX}/{name}", owner=owner, app=app), data))


def delete_saved_search(client: SplunkClient, name: str, *, owner: str, app: str) -> dict[str, Any]:
    """Delete a saved search."""
    return client.write("DELETE", ns_path(f"{_SUFFIX}/{name}", owner=owner, app=app), {})


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
    data: dict[str, Any] = {"trigger_actions": int(bool(trigger_actions))}
    if earliest is not None:
        data["dispatch.earliest_time"] = earliest
    if latest is not None:
        data["dispatch.latest_time"] = latest
    body = client.post(ns_path(f"{_SUFFIX}/{name}/dispatch", owner=owner, app=app), data)
    sid = body.get("sid") if isinstance(body, dict) else None
    if not sid and isinstance(body, dict):
        entries = body.get("entry") or []
        sid = entries[0].get("name") if entries else None
    return {"sid": sid, "dispatched": bool(sid)}


def _apply_optional(
    data: dict[str, Any],
    *,
    description: str | None,
    cron: str | None,
    is_scheduled: bool | None,
) -> None:
    """Add the optional create/update fields that were actually provided."""
    if description is not None:
        data["description"] = description
    if cron is not None:
        data["cron_schedule"] = cron
    if is_scheduled is not None:
        data["is_scheduled"] = int(bool(is_scheduled))


def _unwrap(result: dict[str, Any]) -> dict[str, Any]:
    """Return a dry-run preview unchanged, else normalize the created/updated entry."""
    if result.get("dry_run"):
        return result
    entries = result.get("entry") or []
    return _saved(entries[0]) if entries else result


def _saved(entry: dict[str, Any]) -> dict[str, Any]:
    """Normalize a saved-search entry; owner/app/sharing come from the ``acl`` block."""
    content = entry.get("content") or {}
    acl = entry.get("acl") or {}
    return {
        "name": entry.get("name"),
        "search": content.get("search"),
        "description": content.get("description"),
        "disabled": content.get("disabled"),
        "is_scheduled": content.get("is_scheduled"),
        "cron_schedule": content.get("cron_schedule"),
        "next_scheduled_time": content.get("next_scheduled_time"),
        "app": acl.get("app"),
        "owner": acl.get("owner"),
        "sharing": acl.get("sharing"),
    }
