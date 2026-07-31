"""Deployment-server and deployment-client commands. Shell layer (imports Click).

These are system-level endpoints (not namespaced), so there is no --app/--owner
logic. Writes (serverclass create/update, reload) route through the shared
``do_write`` gate.
"""

from __future__ import annotations

import click

from ..core import deploy as core
from ..core.errors import UsageError
from ..core.parsing import parse_key_value_pairs
from ..core.path import path_segment
from . import output as out
from .context import command
from .write import do_write


@click.group(name="deploy-server")
def deploy_server() -> None:
    """Manage Splunk deployment-server configuration."""


@click.group(name="deploy-client")
def deploy_client() -> None:
    """Inspect Splunk deployment clients."""


@deploy_client.command("list")
@command
def client_list(ctx) -> None:
    """List the deployment clients phoning home."""
    with ctx.client() as c:
        data = core.list_clients(c)
    out.emit(data, ctx.output_mode, ctx.meta())


@deploy_server.group("serverclass")
def serverclass_grp() -> None:
    """Deployment server classes."""


@serverclass_grp.command("list")
@command
def serverclass_list(ctx) -> None:
    """List the configured server classes."""
    with ctx.client() as c:
        data = core.list_serverclasses(c)
    out.emit(data, ctx.output_mode, ctx.meta())


@serverclass_grp.command("get")
@click.argument("name")
@command
def serverclass_get(ctx, name) -> None:
    """Show one server class by name."""
    path_segment(name, label="server class name")
    with ctx.client() as c:
        data = core.get_serverclass(c, name)
    out.emit(data, ctx.output_mode, ctx.meta())


@serverclass_grp.command("create")
@click.argument("name")
@click.option("--set", "_set", multiple=True, metavar="KEY=VALUE", help="Setting (repeatable).")
@command
def serverclass_create(ctx, name, _set) -> None:
    """Create a server class. Requires at least one --set. Gated write."""
    if not _set:
        raise UsageError("Nothing to create. Pass at least one --set KEY=VALUE.")
    path_segment(name, label="server class name")
    settings = parse_key_value_pairs(_set)
    result = do_write(
        ctx,
        action=f"create server class '{name}'",
        audit_event={"action": "deploy.serverclass.create", "name": name},
        run=lambda c: core.create_serverclass(c, name, settings),
    )
    out.emit(result, ctx.output_mode, ctx.meta())


@serverclass_grp.command("update")
@click.argument("name")
@click.option("--set", "_set", multiple=True, metavar="KEY=VALUE", help="Setting (repeatable).")
@command
def serverclass_update(ctx, name, _set) -> None:
    """Update a server class (only the keys you pass). Gated write."""
    if not _set:
        raise UsageError("Nothing to update. Pass at least one --set KEY=VALUE.")
    path_segment(name, label="server class name")
    settings = parse_key_value_pairs(_set)
    result = do_write(
        ctx,
        action=f"update server class '{name}'",
        audit_event={"action": "deploy.serverclass.update", "name": name},
        run=lambda c: core.update_serverclass(c, name, settings),
    )
    out.emit(result, ctx.output_mode, ctx.meta())


@serverclass_grp.command("delete")
@click.argument("name")
@command
def serverclass_delete(ctx, name) -> None:
    """Delete a server class by name. Gated write."""
    path_segment(name, label="server class name")
    result = do_write(
        ctx,
        action=f"delete server class '{name}'",
        audit_event={"action": "deploy.serverclass.delete", "name": name},
        run=lambda c: core.delete_serverclass(c, name),
    )
    out.emit(result, ctx.output_mode, ctx.meta())


@deploy_server.command("reload")
@command
def reload(ctx) -> None:
    """Reload the deployment server's server-class config. Gated write."""
    result = do_write(
        ctx,
        action="reload the deployment server config",
        audit_event={"action": "deploy.reload"},
        run=core.reload_config,
    )
    out.emit(result, ctx.output_mode, ctx.meta())
