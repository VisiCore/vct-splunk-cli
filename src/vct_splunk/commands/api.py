"""`splunk api` — raw read-only REST escape hatch. Shell layer (imports Click)."""

from __future__ import annotations

import click

from ..core import api as core
from ..core.errors import UsageError
from . import output as out
from .context import command


@click.group()
def api() -> None:
    """Raw read-only REST access (escape hatch)."""


@api.command("get")
@click.argument("path")
@click.option(
    "--query", "-q", multiple=True, metavar="KEY=VALUE", help="Query parameter (repeatable)."
)
@command
def get(ctx, path, query) -> None:
    """GET any /services/... endpoint and print the JSON, exactly as sent.

    This is a raw escape hatch, so it does not redact. A named command hides
    secret fields; this one shows the body verbatim, which is the point of an
    escape hatch and means it can print a stored credential. Prefer the named
    command when one exists.
    """
    with ctx.client() as c:
        data = core.api_get(c, path, _parse_query(query))
    out.emit(data, ctx.output_mode, ctx.meta())


def _parse_query(pairs) -> dict[str, str] | None:
    result: dict[str, str] = {}
    for kv in pairs:
        if "=" not in kv:
            raise UsageError(f"--query expects KEY=VALUE (got {kv!r}).")
        key, value = kv.split("=", 1)
        result[key] = value
    return result or None
