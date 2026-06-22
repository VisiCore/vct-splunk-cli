"""`splunk index` commands. Shell layer (imports Click)."""

from __future__ import annotations

import click

from . import audit
from . import indexes as core
from . import output as out
from .context import command


@click.group()
def index() -> None:
    """Splunk indexes."""


@index.command("list")
@command
def list_(ctx) -> None:
    """List indexes."""
    with ctx.client() as c:
        out.emit(core.list_indexes(c), ctx.output_mode, ctx.meta())


@index.command("get")
@click.argument("name")
@command
def get(ctx, name) -> None:
    """Show one index."""
    with ctx.client() as c:
        out.emit(core.get_index(c, name), ctx.output_mode, ctx.meta())


@index.command("create")
@click.argument("name")
@click.option("--max-gb", type=float, default=None, help="Max index size in GB.")
@click.option("--frozen-secs", type=int, default=None, help="Frozen time period in seconds.")
@command
def create(ctx, name, max_gb, frozen_secs) -> None:
    """Create an index. Gated write: --dry-run previews; otherwise confirms or needs --yes."""
    target = ctx.meta()["target"]
    out.confirm_write(ctx, f"create index '{name}'", target)
    with ctx.client() as c:
        result = core.create_index(c, name, max_gb=max_gb, frozen_secs=frozen_secs)
    if not (isinstance(result, dict) and result.get("dry_run")):
        audit.record({"action": "index.create", "name": name, "target": target})
    out.emit(result, ctx.output_mode, ctx.meta())
