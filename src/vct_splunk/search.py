"""Bounded SPL search via a oneshot job. Click-free core.

Conservative defaults (time window, row cap, timeout) keep an agent from launching
an unbounded export by accident.
"""

from __future__ import annotations

from typing import Any

from .client import SplunkClient

_JOBS = "/services/search/jobs"


def run_search(
    client: SplunkClient,
    spl: str,
    *,
    earliest: str = "-24h",
    latest: str = "now",
    max_rows: int = 100,
    timeout: int = 60,
) -> dict[str, Any]:
    query = spl.strip()
    if not (query.startswith("|") or query.lower().startswith("search ")):
        query = "search " + query
    body = client.post(
        _JOBS,
        {
            "search": query,
            "exec_mode": "oneshot",
            "earliest_time": earliest,
            "latest_time": latest,
            "count": max_rows,
        },
        timeout=float(timeout),
    )
    results = body.get("results", []) if isinstance(body, dict) else []
    return {
        "results": results,
        "count": len(results),
        "truncated": len(results) >= max_rows,
        "earliest": earliest,
        "latest": latest,
    }
