"""Cluster status reads: indexer cluster and search-head cluster. Click-free core.

These are system-level (not namespaced) read endpoints that summarize cluster
manager/peer health and search-head cluster membership. Shapes vary by Splunk
role and version, so they are normalized defensively with ``.get``.
"""

from __future__ import annotations

from typing import Any

from .client import SplunkClient
from .errors import NotFoundError


def cluster_status(client: SplunkClient) -> dict[str, Any]:
    """Summarize indexer-cluster manager state, or report it as not configured."""
    try:
        info = _first_content(client.get("/services/cluster/manager/info"))
    except NotFoundError:
        return {"configured": False}
    if not info:
        return {"configured": False}
    return {
        "configured": True,
        "label": info.get("label"),
        "replication_factor": info.get("replication_factor"),
        "search_factor": info.get("search_factor"),
        "indexing_ready": info.get("indexing_ready_flag"),
        "maintenance_mode": info.get("maintenance_mode"),
    }


def shcluster_status(client: SplunkClient) -> dict[str, Any]:
    """Return search-head-cluster state, or report it as not configured."""
    try:
        status = _first_content(client.get("/services/shcluster/status"))
    except NotFoundError:
        return {"configured": False}
    if not status:
        return {"configured": False}
    return {"configured": True, **status}


def _first_content(body: dict[str, Any]) -> dict[str, Any]:
    """Return the first entry's ``content`` block, or an empty dict if absent."""
    entries = body.get("entry") or []
    return (entries[0].get("content") or {}) if entries else {}
