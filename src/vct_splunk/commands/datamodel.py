"""`splunk datamodel accelerate` command. Shell layer (imports Click).

The rest of the ``datamodel`` group (list/get/create/update/delete) is
factory-generated from the ``datamodel`` spec. Toggling acceleration does not fit
the CRUD shape, so it is hand-written here and attached to that generated group in
``cli.py``.
"""

from __future__ import annotations

import click

from ..core import datamodel as core
from ..core.namespace import resolve_ns
from ..core.path import path_segment
from . import output as out
from .context import command
from .write import do_write, refuse_cloud_write


@click.command("accelerate")
@click.argument("name")
@click.option("--enable/--disable", default=True, help="Turn acceleration on (default) or off.")
@command
def datamodel_accelerate(ctx, name, enable) -> None:
    """Toggle acceleration on a data model. Namespaced; gated write; requires an app."""
    path_segment(name, label="data model name")
    verb = "enable" if enable else "disable"
    refuse_cloud_write(ctx, "datamodel", f"accelerate --{verb}")
    owner, app = resolve_ns(ctx.owner, ctx.app, for_write=True)
    result = do_write(
        ctx,
        action=f"{verb} acceleration on data model '{name}' in app '{app}'",
        audit_event={"action": "datamodel.accelerate", "name": name, "enabled": enable, "app": app},
        run=lambda c: core.accelerate(c, name, enabled=enable, owner=owner, app=app),
    )
    out.emit(result, ctx.output_mode, ctx.meta())
