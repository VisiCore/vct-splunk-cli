"""Bounded SPL search via a oneshot job. Click-free core.

Conservative defaults (time window, row cap, timeout) keep an agent from
launching an unbounded export by accident.

The payload construction is split out from :func:`run_search` so the CLI can show
exactly what *would* be sent under ``--dry-run`` without executing anything.
"""

from __future__ import annotations

import json
from typing import Any

from .client import SplunkClient

# Splunk REST endpoint that accepts search jobs.
JOBS_PATH = "/services/search/jobs"
# Streaming export endpoint: returns results directly (no job handle), as
# newline-delimited JSON. Bounded by ``count`` so it can't run away.
EXPORT_PATH = "/services/search/jobs/export"


def normalize_spl(spl: str) -> str:
    """Return *spl* as a runnable search string.

    Splunk's search language needs an explicit leading command. A bare expression
    such as ``index=_internal`` has to be prefixed with ``search``. A query that
    already starts with the ``search`` command or with a generating command
    (``| ...``) is returned unchanged.

    Args:
        spl: The raw search text from the user.

    Returns:
        The search string Splunk will actually run.
    """
    query = spl.strip()
    # Compare the first whitespace-delimited word rather than the literal prefix
    # "search ", so a tab/newline after the command (e.g. "search\tindex=...")
    # is recognized as already-normalized instead of being double-prefixed.
    first_word = query.split(maxsplit=1)[0].lower() if query else ""
    if query.startswith("|") or first_word == "search":
        return query
    return "search " + query


def build_search_payload(spl: str, *, earliest: str, latest: str, max_rows: int) -> dict[str, Any]:
    """Build the form body for a oneshot search job.

    Pulled out of :func:`run_search` so both the real request and the
    ``--dry-run`` preview are built from the same code — the preview can never
    drift from what actually gets sent.

    Args:
        spl: The search text (normalized via :func:`normalize_spl`).
        earliest: Start of the search time window (Splunk relative-time syntax).
        latest: End of the search time window.
        max_rows: Upper bound on returned rows, sent as Splunk's ``count``.

    Returns:
        The form fields to POST to :data:`JOBS_PATH`.
    """
    return {
        "search": normalize_spl(spl),
        # "oneshot" makes Splunk run the search and return the results inline in
        # the response, instead of handing back a job handle we'd have to poll.
        "exec_mode": "oneshot",
        "earliest_time": earliest,
        "latest_time": latest,
        "count": max_rows,
    }


def run_search(
    client: SplunkClient,
    spl: str,
    *,
    earliest: str = "-24h",
    latest: str = "now",
    max_rows: int = 100,
    timeout: int = 60,
) -> dict[str, Any]:
    """Run *spl* as a bounded oneshot search and return its results.

    Args:
        client: An open Splunk client.
        spl: The search string (normalized via :func:`normalize_spl`).
        earliest: Start of the search time window (Splunk relative-time syntax).
        latest: End of the search time window.
        max_rows: Upper bound on returned rows (Splunk ``count``). Callers should
            pass a value ``>= 1``; ``0`` means "unlimited" to Splunk, which the
            CLI deliberately forbids.
        timeout: Per-request timeout in seconds.

    Returns:
        A dict with the ``results`` list, their ``count``, a ``truncated`` flag
        (True when the row cap was reached and more may exist), and the resolved
        time window.
    """
    payload = build_search_payload(spl, earliest=earliest, latest=latest, max_rows=max_rows)
    body = client.post(JOBS_PATH, payload, timeout=float(timeout))
    results = body.get("results", []) if isinstance(body, dict) else []
    return {
        "results": results,
        "count": len(results),
        # We asked Splunk for at most max_rows rows; getting exactly that many
        # back is the signal that the result set was capped and more may exist.
        "truncated": len(results) >= max_rows,
        "earliest": earliest,
        "latest": latest,
    }


def build_export_payload(spl: str, *, earliest: str, latest: str, max_rows: int) -> dict[str, Any]:
    """Build the form body for the streaming export endpoint.

    Like :func:`build_search_payload` but without ``exec_mode`` (export is not a
    job). ``count`` still bounds the rows, so the export stays capped. Split out
    so the ``--dry-run`` preview matches the real request exactly.
    """
    return {
        "search": normalize_spl(spl),
        "earliest_time": earliest,
        "latest_time": latest,
        "count": max_rows,
    }


def run_export(
    client: SplunkClient,
    spl: str,
    *,
    earliest: str = "-24h",
    latest: str = "now",
    max_rows: int = 100,
    timeout: int = 60,
) -> dict[str, Any]:
    """Stream a bounded result set from the export endpoint (no job is created).

    The export endpoint answers with newline-delimited JSON objects rather than
    one JSON document, so the JSON-only client hands the body back as raw text;
    we parse each line and collect the result rows. ``count`` caps the rows, so
    an automated caller cannot trigger an unbounded export.

    Returns:
        The same shape as :func:`run_search`: ``results``, ``count``,
        ``truncated``, and the resolved time window.
    """
    payload = build_export_payload(spl, earliest=earliest, latest=latest, max_rows=max_rows)
    body = client.post(EXPORT_PATH, payload, timeout=float(timeout))
    results = _parse_export(body.get("raw", "") if isinstance(body, dict) else "")
    return {
        "results": results,
        "count": len(results),
        "truncated": len(results) >= max_rows,
        "earliest": earliest,
        "latest": latest,
    }


def _parse_export(raw: str) -> list[dict[str, Any]]:
    """Parse newline-delimited export JSON into a list of result rows.

    Each non-empty line is one JSON object; result lines carry a ``result`` key
    (other lines are previews or messages and are skipped).
    """
    rows: list[dict[str, Any]] = []
    for line in raw.splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            obj = json.loads(text)
        except ValueError:
            continue
        if isinstance(obj, dict) and "result" in obj:
            rows.append(obj["result"])
    return rows
