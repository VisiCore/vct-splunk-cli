"""`splunk saved-search` commands. Shell layer (imports Click).

The CRUD verbs come from the generic factory (the :data:`SAVED_SEARCH` spec);
only ``run`` (dispatch) is hand-written, because dispatching is an action, not
CRUD. Saved searches are namespaced: reads default to the ``-`` wildcard,
writes require an explicit ``--app`` (or ``$SPLUNK_APP``) so an object is never
created in the default ``search`` app by accident.
"""

from __future__ import annotations

import click

from ..core import saved_searches as core
from ..core.errors import UnsupportedBackendError
from ..core.namespace import ns_path, resolve_ns
from . import output as out
from .context import command
from .factory import build_group
from .registry import SAVED_SEARCH

saved_search = build_group(SAVED_SEARCH)


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

    Requires an app: Splunk rejects a dispatch POST to a wildcarded namespace
    ("Cannot edit/create a saved search for wildcarded users or applications"),
    so the namespace resolves like a write — explicit app, owner defaulting to
    ``nobody`` (found live against Splunk 10.2).
    """
    if ctx.backend == "cloud":
        raise UnsupportedBackendError("saved-search", "run", "cloud")
    owner, app = resolve_ns(ctx.owner, ctx.app, for_write=True)
    if ctx.dry_run:
        # Built by the same core function as the real request, so the preview
        # can never disagree with what would be sent.
        preview = {
            "dry_run": True,
            "request": {
                "method": "POST",
                "path": ns_path(f"saved/searches/{name}/dispatch", owner=owner, app=app),
                "body": core.build_dispatch_payload(
                    trigger_actions=trigger_actions, earliest=earliest, latest=latest
                ),
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
