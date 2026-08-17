"""`splunk config` read-only commands. Shell layer (imports Click)."""

from __future__ import annotations

import click

from ..core import config as core
from ..core.namespace import resolve_ns
from . import output as out
from .context import command


@click.group()
def config() -> None:
    """Read visible Splunk configuration files and stanzas."""


@config.command("list")
@click.argument("file", required=False)
@command
def list_(ctx, file: str | None) -> None:
    """List visible configuration files, or every stanza in FILE."""
    owner, app = resolve_ns(ctx.owner, ctx.app, for_write=False)
    with ctx.client() as c:
        data = (
            core.list_stanzas(c, file, owner=owner, app=app)
            if file is not None
            else core.list_files(c, owner=owner, app=app)
        )
    out.emit(data, ctx.output_mode, ctx.meta())


@config.command("get")
@click.argument("file")
@click.argument("stanza")
@command
def get(ctx, file: str, stanza: str) -> None:
    """Show one stanza's properties from FILE."""
    owner, app = resolve_ns(ctx.owner, ctx.app, for_write=False)
    with ctx.client() as c:
        data = core.get_stanza(c, file, stanza, owner=owner, app=app)
    out.emit(data, ctx.output_mode, ctx.meta())
