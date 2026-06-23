"""Cluster status reads: indexer cluster and search-head cluster. Click-free core.

These are system-level (not namespaced) read endpoints that summarize cluster
manager/peer health and search-head cluster membership. Shapes vary by Splunk
role and version, so they are normalized defensively with ``.get``.
"""

from __future__ import annotations

from typing import Any

from .client import SplunkClient


def cluster_status(client: SplunkClient) -> dict[str, Any]:
    """Summarize indexer-cluster manager state plus peer health.

    Reads ``/services/cluster/config`` for the local node's cluster config and
    ``/services/cluster/master/info`` for manager-side status. Either may be
    empty on a node that is not a cluster manager; missing pieces are reported
    as null rather than failing.
    """
    config = _first_content(client.get("/services/cluster/config"))
    info = _first_content(client.get("/services/cluster/master/info"))
    return {
        "mode": config.get("mode"),
        "manager_uri": config.get("manager_uri") or config.get("master_uri"),
        "replication_factor": config.get("replication_factor"),
        "search_factor": config.get("search_factor"),
        "indexing_ready": info.get("indexing_ready_flag"),
        "maintenance_mode": info.get("maintenance_mode"),
    }


def shcluster_status(client: SplunkClient) -> list[dict[str, Any]]:
    """List search-head cluster members and their roles.

    Reads ``/services/shcluster/member/members``; each entry is one member of
    the search-head cluster.
    """
    return [_member(e) for e in client.get_collection("/services/shcluster/member/members")]


def _member(entry: dict[str, Any]) -> dict[str, Any]:
    c = entry.get("content") or {}
    return {
        "name": entry.get("name"),
        "label": c.get("label"),
        "status": c.get("status"),
        "is_captain": c.get("is_captain"),
        "site": c.get("site"),
    }


def _first_content(body: dict[str, Any]) -> dict[str, Any]:
    """Return the first entry's ``content`` block, or an empty dict if absent."""
    entries = body.get("entry") or []
    return (entries[0].get("content") or {}) if entries else {}
