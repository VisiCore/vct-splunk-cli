"""`splunk lookup` commands: lookup table file upload. Shell layer (imports Click).

Lookup *definitions* are the factory-generated ``lookup-definition`` group. This
group adds the one operation that does not fit the CRUD shape: uploading the CSV
table file itself.
"""

from __future__ import annotations

from pathlib import Path

import click

from ..core import lookups as core
from ..core.namespace import resolve_ns
from . import output as out
from .context import command
from .write import do_write


@click.group(name="lookup")
def lookup() -> None:
    """Lookup table files (lookup definitions live in the 'lookup-definition' group)."""


@lookup.command("upload")
@click.option("--file", "file", required=True, type=click.Path(exists=True), help="Local CSV path.")
@command
def upload(ctx, file) -> None:
    """Upload a CSV lookup table file into an app. Namespaced; gated write; requires an app."""
    owner, app = resolve_ns(ctx.owner, ctx.app, for_write=True)
    filename = Path(file).name
    contents = Path(file).read_text(encoding="utf-8")
    result = do_write(
        ctx,
        action=f"upload lookup file '{filename}' into app '{app}'",
        audit_event={"action": "lookup.upload", "filename": filename, "app": app},
        run=lambda c: core.upload_lookup(c, filename, contents, owner=owner, app=app),
    )
    out.emit(result, ctx.output_mode, ctx.meta())
