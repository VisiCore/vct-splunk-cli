"""`splunk shcluster` commands (search-head cluster). Shell layer (imports Click)."""

from __future__ import annotations

import click

from ..core import cluster as core
from . import output as out
from .context import command


@click.group()
def shcluster() -> None:
    """Search-head cluster."""


@shcluster.command("status")
@command
def status(ctx) -> None:
    """List search-head cluster members and their roles."""
    with ctx.client() as c:
        data = core.shcluster_status(c)
    out.emit(data, ctx.output_mode, ctx.meta())
