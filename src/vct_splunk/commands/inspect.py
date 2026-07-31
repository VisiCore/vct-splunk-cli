"""`splunk inspect` -- report the deduced backend and what it supports."""

from __future__ import annotations

import click

from ..core.backends import inspect_report
from . import output as out
from .context import command


@click.command("inspect")
@command
def inspect(ctx) -> None:
    """Report the backend deduced from SPLUNK_URL and the operations it supports.

    The backend is deduced from the URL, never chosen -- this command just *shows*
    it for anyone who explicitly wants to know which target (Enterprise or Cloud) a
    given SPLUNK_URL resolves to and which operations exist there. It reads a static
    capability map: offline, no live instance touched. Unsupported operations are
    named, so a caller never falls through to an unofficial endpoint.
    """
    out.emit(inspect_report(ctx.base_url), ctx.output_mode, ctx.meta())
