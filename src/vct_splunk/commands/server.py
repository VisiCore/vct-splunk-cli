"""`splunk server` commands. Shell layer (imports Click)."""

from __future__ import annotations

import click

from ..core import server as core
from . import output as out
from .context import command


@click.group()
def server() -> None:
    """Splunk server."""


@server.command("info")
@command
def info(ctx) -> None:
    """Show server identity and version (also proves connectivity + auth)."""
    with ctx.client() as c:
        data = core.get_server_info(c)
    out.emit(data, ctx.output_mode, ctx.meta())
