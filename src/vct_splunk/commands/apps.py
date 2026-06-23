"""`splunk app install` command. Shell layer (imports Click).

The rest of the ``app`` group (list/get/delete/enable/disable) is factory-generated
from the ``app`` spec. Install does not fit the CRUD shape, so it is hand-written
here and attached to that generated group in ``cli.py``.
"""

from __future__ import annotations

import click

from ..core import apps as core
from ..core.errors import UsageError
from . import output as out
from .context import command
from .write import do_write


@click.command("install")
@click.option("--file", "file", default=None, help="Local app archive path (.tar.gz/.spl).")
@click.option("--url", "url", default=None, help="http(s) URL to an app archive.")
@click.option("--update/--no-update", default=False, help="Overwrite an already-installed app.")
@command
def app_install(ctx, file, url, update) -> None:
    """Install an app from a local --file or a --url. Gated write."""
    if bool(file) == bool(url):
        raise UsageError("Pass exactly one of --file or --url.")
    source = file or url
    result = do_write(
        ctx,
        action=f"install app from '{source}'" + (" (overwrite)" if update else ""),
        audit_event={"action": "app.install", "source": source, "update": update},
        run=lambda c: core.install_app(c, source, update=update),
    )
    out.emit(result, ctx.output_mode, ctx.meta())
