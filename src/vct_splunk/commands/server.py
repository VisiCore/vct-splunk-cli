"""`splunk server` commands. Shell layer (imports Click)."""

from __future__ import annotations

import click

from ..core import server as core
from ..core.errors import UsageError
from . import output as out
from .context import command
from .write import do_write


@click.group()
def server() -> None:
    """Splunk server."""


@server.command("info")
@command
def info(ctx) -> None:
    """Show server identity and version (also proves connectivity + auth)."""
    with ctx.client() as c:
        data = core.get_server_info(c)
    out.emit(data, ctx.output_mode, ctx.meta())


@server.command("restart")
@command
def restart(ctx) -> None:
    """Restart the Splunk server. Gated write (interrupts the whole instance)."""
    result = do_write(
        ctx,
        action="restart the Splunk server (interrupts the whole instance)",
        audit_event={"action": "server.restart"},
        run=core.restart_server,
    )
    out.emit(result, ctx.output_mode, ctx.meta())


@server.group("settings")
def settings() -> None:
    """Splunk server general settings."""


@settings.command("get")
@command
def settings_get(ctx) -> None:
    """Show the server's general settings."""
    with ctx.client() as c:
        data = core.get_settings(c)
    out.emit(data, ctx.output_mode, ctx.meta())


@settings.command("set")
@click.option(
    "--set", "_set", multiple=True, metavar="KEY=VALUE", help="Setting to change (repeatable)."
)
@command
def settings_set(ctx, _set) -> None:
    """Change server settings (only the keys you pass). Gated write."""
    if not _set:
        raise UsageError("Nothing to set. Pass at least one --set KEY=VALUE.")
    changes: dict[str, str] = {}
    for pair in _set:
        key, _, val = pair.partition("=")
        changes[key] = val
    result = do_write(
        ctx,
        action=f"change server settings: {', '.join(sorted(changes))}",
        audit_event={"action": "server.settings.set", "keys": sorted(changes)},
        run=lambda c: core.set_settings(c, changes),
    )
    out.emit(result, ctx.output_mode, ctx.meta())
