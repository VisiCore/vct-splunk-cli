"""`splunk api` — raw read-only REST escape hatch. Shell layer (imports Click)."""

from __future__ import annotations

import click

from . import api as core
from . import output as out
from .context import command
from .errors import UsageError


@click.group()
def api() -> None:
    """Raw read-only REST access (escape hatch)."""


@api.command("get")
@click.argument("path")
@click.option("--query", "-q", multiple=True, metavar="K=V", help="Query parameter (repeatable).")
@command
def get(ctx, path, query) -> None:
    """GET any /services/... endpoint and print the JSON."""
    with ctx.client() as c:
        data = core.api_get(c, path, _parse_query(query))
    out.emit(data, ctx.output_mode, ctx.meta())


def _parse_query(pairs) -> dict[str, str] | None:
    result: dict[str, str] = {}
    for kv in pairs:
        if "=" not in kv:
            raise UsageError(f"--query expects K=V (got {kv!r}).")
        key, value = kv.split("=", 1)
        result[key] = value
    return result or None
