"""Output rendering, error mapping, and write-gating. Shell layer (imports Click).

Keeps stdout pure data and sends everything else (errors, prompts) to stderr, so
`splunk ... --output json | jq` never chokes.
"""

from __future__ import annotations

import json
import sys
from typing import Any

import click

from .errors import SplunkError, UsageError


def resolve_mode(output: str | None, table: bool) -> str:
    if output:
        return output
    if table:
        return "table"
    return "table" if sys.stdout.isatty() else "json"


def fail(exc: SplunkError) -> None:
    payload: dict[str, Any] = {"error": {"code": exc.code, "message": exc.message}}
    if exc.details is not None:
        payload["error"]["details"] = exc.details
    click.echo(json.dumps(payload, default=str), err=True)
    raise SystemExit(exc.exit_code)


def emit(data: Any, mode: str, meta: dict[str, Any] | None = None) -> None:
    if mode == "json":
        click.echo(json.dumps({"data": data, "meta": meta or {}}, indent=2, default=str))
    else:
        click.echo(_table(data))


def _table(data: Any) -> str:
    rows = [r for r in (data if isinstance(data, list) else [data]) if isinstance(r, dict)]
    if not rows:
        return "(no results)" if isinstance(data, list) else json.dumps(data, indent=2, default=str)
    cols = list(rows[0].keys())
    width = {c: max(len(str(c)), max(len(str(r.get(c, ""))) for r in rows)) for c in cols}
    head = "  ".join(str(c).upper().ljust(width[c]) for c in cols)
    lines = ["  ".join(str(r.get(c, "")).ljust(width[c]) for c in cols) for r in rows]
    return "\n".join([head, *lines])


def confirm_write(ctx: Any, action: str, target: str | None) -> None:
    """Gate a mutation. Dry-run and --yes skip the prompt; non-interactive without
    --yes fails fast (never hangs an agent on a hidden prompt)."""
    if ctx.dry_run or ctx.yes:
        return
    if not (sys.stdin.isatty() and sys.stderr.isatty()):
        raise UsageError(f"Refusing to {action} on {target} without --yes (non-interactive).")
    click.confirm(f"About to {action} on {target}. Continue?", abort=True, err=True)


def resolve_query(query: str | None, file_: Any, stdin_token: str | None) -> str:
    chosen = [s for s in (query, file_, stdin_token) if s]
    if len(chosen) != 1:
        raise UsageError("Provide exactly one of --query, --file, or '-' (stdin).")
    if query:
        return query
    if file_:
        return file_.read()
    if stdin_token == "-":
        return sys.stdin.read()
    raise UsageError("Use '-' to read the query from stdin.")
