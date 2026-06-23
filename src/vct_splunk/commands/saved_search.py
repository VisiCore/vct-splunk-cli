"""`splunk saved-search` commands. Shell layer (imports Click).

Saved searches are namespaced. Reads default to the ``-`` wildcard (all owners
and apps); writes require an explicit ``--app`` (or ``$SPLUNK_APP``) so an object
is never created in the default ``search`` app by accident.
"""

from __future__ import annotations

import click

from ..core import saved_searches as core
from ..core.namespace import ns_path, resolve_ns
from . import output as out
from .context import command
from .write import do_write


@click.group(name="saved-search")
def saved_search() -> None:
    """Splunk saved searches (namespaced by owner + app)."""


@saved_search.command("list")
@command
def list_(ctx) -> None:
    """List saved searches (use --app/--owner to narrow the namespace)."""
    owner, app = resolve_ns(ctx.owner, ctx.app, for_write=False)
    with ctx.client() as c:
        out.emit(core.list_saved_searches(c, owner=owner, app=app), ctx.output_mode, ctx.meta())


@saved_search.command("get")
@click.argument("name")
@command
def get(ctx, name) -> None:
    """Show one saved search."""
    owner, app = resolve_ns(ctx.owner, ctx.app, for_write=False)
    with ctx.client() as c:
        out.emit(core.get_saved_search(c, name, owner=owner, app=app), ctx.output_mode, ctx.meta())


@saved_search.command("create")
@click.argument("name")
@click.option("--search", "search_", required=True, help="SPL for the saved search.")
@click.option("--description", default=None, help="Description.")
@click.option("--cron", default=None, help="Cron schedule, e.g. '0 6 * * *'.")
@click.option("--scheduled/--no-scheduled", "is_scheduled", default=None, help="Enable scheduling.")
@command
def create(ctx, name, search_, description, cron, is_scheduled) -> None:
    """Create a saved search. Gated write; requires an app (never 'search' by default)."""
    owner, app = resolve_ns(ctx.owner, ctx.app, for_write=True)
    result = do_write(
        ctx,
        action=f"create saved search '{name}' in app '{app}'",
        audit_event={"action": "saved_search.create", "name": name, "app": app, "owner": owner},
        run=lambda c: core.create_saved_search(
            c,
            name,
            owner=owner,
            app=app,
            search=search_,
            description=description,
            cron=cron,
            is_scheduled=is_scheduled,
        ),
    )
    out.emit(result, ctx.output_mode, ctx.meta())


@saved_search.command("update")
@click.argument("name")
@click.option("--search", "search_", default=None, help="New SPL.")
@click.option("--description", default=None, help="New description.")
@click.option("--cron", default=None, help="New cron schedule.")
@click.option(
    "--scheduled/--no-scheduled", "is_scheduled", default=None, help="Enable/disable scheduling."
)
@command
def update(ctx, name, search_, description, cron, is_scheduled) -> None:
    """Update a saved search (only the fields you pass). Gated write; requires an app."""
    owner, app = resolve_ns(ctx.owner, ctx.app, for_write=True)
    result = do_write(
        ctx,
        action=f"update saved search '{name}' in app '{app}'",
        audit_event={"action": "saved_search.update", "name": name, "app": app, "owner": owner},
        run=lambda c: core.update_saved_search(
            c,
            name,
            owner=owner,
            app=app,
            search=search_,
            description=description,
            cron=cron,
            is_scheduled=is_scheduled,
        ),
    )
    out.emit(result, ctx.output_mode, ctx.meta())


@saved_search.command("delete")
@click.argument("name")
@command
def delete(ctx, name) -> None:
    """Delete a saved search. Gated write; requires an app."""
    owner, app = resolve_ns(ctx.owner, ctx.app, for_write=True)
    result = do_write(
        ctx,
        action=f"delete saved search '{name}' in app '{app}'",
        audit_event={"action": "saved_search.delete", "name": name, "app": app, "owner": owner},
        run=lambda c: core.delete_saved_search(c, name, owner=owner, app=app),
    )
    out.emit(result, ctx.output_mode, ctx.meta())


@saved_search.command("run")
@click.argument("name")
@click.option("--trigger-actions", is_flag=True, help="Fire alert actions if configured.")
@click.option("--earliest", default=None, help="Dispatch earliest time (override).")
@click.option("--latest", default=None, help="Dispatch latest time (override).")
@command
def run(ctx, name, trigger_actions, earliest, latest) -> None:
    """Dispatch a saved search and return the new job's SID.

    Dispatching creates a server-side job like ``search run``; it is not a config
    change, so it is not gated. ``--dry-run`` previews the request instead.
    """
    owner, app = resolve_ns(ctx.owner, ctx.app, for_write=False)
    if ctx.dry_run:
        preview = {
            "dry_run": True,
            "request": {
                "method": "POST",
                "path": ns_path(f"saved/searches/{name}/dispatch", owner=owner, app=app),
                "body": {"trigger_actions": int(trigger_actions)},
            },
            "target": ctx.meta()["target"],
        }
        out.emit(preview, ctx.output_mode, ctx.meta())
        return
    with ctx.client() as c:
        data = core.dispatch_saved_search(
            c,
            name,
            owner=owner,
            app=app,
            trigger_actions=trigger_actions,
            earliest=earliest,
            latest=latest,
        )
    out.emit(data, ctx.output_mode, ctx.meta())
