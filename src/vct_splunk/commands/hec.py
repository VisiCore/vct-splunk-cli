"""`splunk hec` commands: HEC extras the CRUD factory cannot express.

Token CRUD is the factory-generated ``hec-token`` group. This group adds the two
operations that do not fit that shape: rotating a token's secret and toggling the
global HEC listener on or off.
"""

from __future__ import annotations

import click

from ..core import hec as core
from ..core.path import path_segment
from . import output as out
from .context import command
from .write import do_write


@click.group(name="hec")
def hec() -> None:
    """HTTP Event Collector extras (token CRUD lives in the 'hec-token' group)."""


@hec.command("rotate")
@click.argument("name")
@command
def rotate(ctx, name) -> None:
    """Mint a fresh secret for a HEC token, printing the new value. Gated write.

    The new token value is printed (that is the point of rotation) but is never
    written to the audit log, which records only the action and token name.
    """
    path_segment(name, label="HEC token name")
    result = do_write(
        ctx,
        action=f"rotate HEC token '{name}' (mints a new secret)",
        audit_event={"action": "hec.rotate", "name": name},
        run=lambda c: core.rotate_token(c, name),
    )
    out.emit(result, ctx.output_mode, ctx.meta())


@hec.command("global-enable")
@command
def global_enable(ctx) -> None:
    """Enable HEC globally (the 'http' input stanza). Gated write."""
    result = do_write(
        ctx,
        action="enable HEC globally",
        audit_event={"action": "hec.global_enable"},
        run=lambda c: core.set_global(c, enabled=True),
    )
    out.emit(result, ctx.output_mode, ctx.meta())


@hec.command("global-disable")
@command
def global_disable(ctx) -> None:
    """Disable HEC globally (the 'http' input stanza). Gated write."""
    result = do_write(
        ctx,
        action="disable HEC globally",
        audit_event={"action": "hec.global_disable"},
        run=lambda c: core.set_global(c, enabled=False),
    )
    out.emit(result, ctx.output_mode, ctx.meta())
