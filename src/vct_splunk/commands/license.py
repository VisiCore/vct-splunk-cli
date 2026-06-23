"""`splunk license` commands (licensing reads). Shell layer (imports Click)."""

from __future__ import annotations

import click

from ..core import license as core
from . import output as out
from .context import command


@click.group()
def license() -> None:
    """Splunk licensing."""


@license.command("list")
@command
def list_(ctx) -> None:
    """List installed licenses."""
    with ctx.client() as c:
        data = core.list_licenses(c)
    out.emit(data, ctx.output_mode, ctx.meta())


@license.command("get")
@click.argument("name")
@command
def get(ctx, name) -> None:
    """Show one license by its name (license hash)."""
    with ctx.client() as c:
        data = core.get_license(c, name)
    out.emit(data, ctx.output_mode, ctx.meta())


@license.command("usage")
@command
def usage(ctx) -> None:
    """Report per-pool license usage (quota vs. used volume)."""
    with ctx.client() as c:
        data = core.license_usage(c)
    out.emit(data, ctx.output_mode, ctx.meta())
