"""Deployment server operations: clients, server classes, reload. Click-free core.

The deployment server hands out app bundles to deployment clients. These are
system-level endpoints under ``/services/deployment/server`` -- not namespaced,
so there is no owner/app logic. Reads normalize the Splunk ``entry[].content``
envelope; writes are gated through the command layer's ``do_write``.
"""

from __future__ import annotations

from typing import Any

from .client import SplunkClient
from .errors import NotFoundError
from .path import path_segment

_CLIENTS = "/services/deployment/server/clients"
_SERVERCLASSES = "/services/deployment/server/serverclasses"
_RELOAD = "/services/deployment/server/config/_reload"


def list_clients(client: SplunkClient) -> list[dict[str, Any]]:
    """List the deployment clients currently phoning home."""
    return [_named(e) for e in client.get_collection(_CLIENTS)]


def list_serverclasses(client: SplunkClient) -> list[dict[str, Any]]:
    """List the configured server classes."""
    return [_named(e) for e in client.get_collection(_SERVERCLASSES)]


def get_serverclass(client: SplunkClient, name: str) -> dict[str, Any]:
    """Show one server class by name."""
    encoded = path_segment(name, label="server class name")
    entries = client.get(f"{_SERVERCLASSES}/{encoded}").get("entry") or []
    if not entries:
        raise NotFoundError(f"Server class {name!r} not found.")
    return _named(entries[0])


def create_serverclass(client: SplunkClient, name: str, settings: dict[str, Any]) -> dict[str, Any]:
    """Create a server class with the given form settings (a gated write)."""
    path_segment(name, label="server class name")
    return _unwrap(client.write("POST", _SERVERCLASSES, {"name": name, **settings}))


def update_serverclass(client: SplunkClient, name: str, settings: dict[str, Any]) -> dict[str, Any]:
    """Update a server class, sending only the changed settings (a gated write)."""
    encoded = path_segment(name, label="server class name")
    return _unwrap(client.write("POST", f"{_SERVERCLASSES}/{encoded}", settings))


def reload_config(client: SplunkClient) -> dict[str, Any]:
    """Reload the deployment server's server-class configuration (a gated write)."""
    return client.write("POST", _RELOAD, {})


def _unwrap(result: dict[str, Any]) -> dict[str, Any]:
    """Return a dry-run preview unchanged, else normalize the affected server class."""
    if result.get("dry_run"):
        return result
    entries = result.get("entry") or []
    return _named(entries[0]) if entries else result


def _named(entry: dict[str, Any]) -> dict[str, Any]:
    """Flatten one Splunk entry into ``name`` plus its content block."""
    return {"name": entry.get("name"), **(entry.get("content") or {})}
