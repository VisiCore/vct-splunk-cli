"""`splunk lookup` commands: lookup table file upload. Shell layer (imports Click).

Lookup *definitions* are the factory-generated ``lookup-definition`` group. This
group adds the one operation that does not fit the CRUD shape: uploading the CSV
table file itself.
"""

from __future__ import annotations

from pathlib import PurePath

import click

from ..core import lookups as core
from ..core.namespace import resolve_ns
from . import output as out
from .context import command
from .write import do_write, refuse_cloud_write


@click.group(name="lookup")
def lookup() -> None:
    """Lookup table files (lookup definitions live in the 'lookup-definition' group)."""


@lookup.command("upload")
@click.option(
    "--server-file",
    required=True,
    help="CSV staging path readable by splunkd on the Splunk server.",
)
@command
def upload(ctx, server_file) -> None:
    """Install a staged CSV lookup table into an app. Namespaced, gated, and app-required."""
    refuse_cloud_write(ctx, "lookup", "upload")
    owner, app = resolve_ns(ctx.owner, ctx.app, for_write=True)
    filename = PurePath(server_file).name
    result = do_write(
        ctx,
        action=f"upload lookup file '{filename}' into app '{app}'",
        audit_event={"action": "lookup.upload", "filename": filename, "app": app},
        run=lambda c: core.upload_lookup(c, filename, server_file, owner=owner, app=app),
    )
    out.emit(result, ctx.output_mode, ctx.meta())
