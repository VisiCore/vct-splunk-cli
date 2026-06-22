"""`splunk health` commands. Shell layer (imports Click)."""

from __future__ import annotations

import click

from . import health as core
from . import output as out
from .context import command


@click.group()
def health() -> None:
    """Health checks."""


@health.command("check")
@command
def check(ctx) -> None:
    """Check Splunk health. Exits non-zero if any finding is warn or fail."""
    with ctx.client() as c:
        verdicts = core.check_health(c)
    out.emit(verdicts, ctx.output_mode, ctx.meta())
    if any(v["finding"] in ("warn", "fail") for v in verdicts):
        raise SystemExit(1)
