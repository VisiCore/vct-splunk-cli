"""`splunk inspect` -- report the active backend and what it supports."""

from __future__ import annotations

import click

from ..core.backends import inspect_backend
from . import output as out
from .context import command


@click.command("inspect")
@click.option(
    "--backend",
    type=click.Choice(["enterprise", "cloud"]),
    default=None,
    help="Backend to inspect (default: $SPLUNK_BACKEND, else enterprise).",
)
@command
def inspect(ctx, backend) -> None:
    """Report the active backend (enterprise/cloud) and the operations it supports.

    Reads a static capability map -- it works offline and does not touch the live
    instance. Unsupported operations are named explicitly, so a caller never falls
    through to an unofficial endpoint.
    """
    out.emit(inspect_backend(backend), ctx.output_mode, ctx.meta())
