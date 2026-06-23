"""`splunk index` commands. Shell layer (imports Click)."""

from __future__ import annotations

import click

from ..core import indexes as core
from ..core.errors import UsageError
from . import output as out
from .context import AliasedGroup, command
from .write import do_write


# Splunk-CLI familiarity: add/edit/remove resolve to create/update/delete.
@click.group(cls=AliasedGroup, aliases={"add": "create", "edit": "update", "remove": "delete"})
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
    """Create an index. Gated write (--dry-run previews; --yes when non-interactive)."""
    result = do_write(
        ctx,
        action=f"create index '{name}'",
        audit_event={"action": "index.create", "name": name},
        run=lambda c: core.create_index(c, name, max_gb=max_gb, frozen_secs=frozen_secs),
    )
    out.emit(result, ctx.output_mode, ctx.meta())


@index.command("update")
@click.argument("name")
@click.option("--max-gb", type=float, default=None, help="Max index size in GB.")
@click.option("--frozen-secs", type=int, default=None, help="Frozen time period in seconds.")
@command
def update(ctx, name, max_gb, frozen_secs) -> None:
    """Update an index's settings (only the options you pass). Gated write."""
    if max_gb is None and frozen_secs is None:
        raise UsageError("Nothing to update. Pass --max-gb and/or --frozen-secs.")
    result = do_write(
        ctx,
        action=f"update index '{name}'",
        audit_event={"action": "index.update", "name": name},
        run=lambda c: core.update_index(c, name, max_gb=max_gb, frozen_secs=frozen_secs),
    )
    out.emit(result, ctx.output_mode, ctx.meta())


@index.command("delete")
@click.argument("name")
@command
def delete(ctx, name) -> None:
    """Delete an index and its data. Gated write."""
    result = do_write(
        ctx,
        action=f"delete index '{name}'",
        audit_event={"action": "index.delete", "name": name},
        run=lambda c: core.delete_index(c, name),
    )
    out.emit(result, ctx.output_mode, ctx.meta())


@index.command("enable")
@click.argument("name")
@command
def enable(ctx, name) -> None:
    """Enable an index. Gated write."""
    result = do_write(
        ctx,
        action=f"enable index '{name}'",
        audit_event={"action": "index.enable", "name": name},
        run=lambda c: core.enable_index(c, name),
    )
    out.emit(result, ctx.output_mode, ctx.meta())


@index.command("disable")
@click.argument("name")
@command
def disable(ctx, name) -> None:
    """Disable an index. Gated write."""
    result = do_write(
        ctx,
        action=f"disable index '{name}'",
        audit_event={"action": "index.disable", "name": name},
        run=lambda c: core.disable_index(c, name),
    )
    out.emit(result, ctx.output_mode, ctx.meta())
