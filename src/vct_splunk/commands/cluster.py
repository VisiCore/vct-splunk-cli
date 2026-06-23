"""`splunk cluster` commands (indexer cluster status). Shell layer (imports Click)."""

from __future__ import annotations

import click

from ..core import cluster as core
from . import output as out
from .context import command


@click.group()
def cluster() -> None:
    """Indexer cluster."""


@cluster.command("status")
@command
def status(ctx) -> None:
    """Summarize indexer-cluster manager and peer health."""
    with ctx.client() as c:
        data = core.cluster_status(c)
    out.emit(data, ctx.output_mode, ctx.meta())
