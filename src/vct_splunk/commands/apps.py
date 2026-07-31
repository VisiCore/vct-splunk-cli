"""`splunk app install` command. Shell layer (imports Click).

The rest of the ``app`` group (list/get/delete/enable/disable) is factory-generated
from the ``app`` spec. Install does not fit the CRUD shape, so it is hand-written
here and attached to that generated group in ``cli.py``.
"""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

import click

from ..core import apps as core
from ..core.errors import UsageError
from . import output as out
from .context import command
from .write import do_write


@click.command("install")
@click.option(
    "--server-file",
    default=None,
    help="App archive path readable by splunkd on the server (.tar.gz/.spl).",
)
@click.option("--url", default=None, help="http(s) app archive URL reachable by splunkd.")
@click.option("--update/--no-update", default=False, help="Overwrite an already-installed app.")
@command
def app_install(ctx, server_file, url, update) -> None:
    """Install an app from a splunkd-readable server path or URL. Gated write."""
    if bool(server_file) == bool(url):
        raise UsageError("Pass exactly one of --server-file or --url.")
    source = server_file or url
    safe_source = _safe_source(source, is_url=bool(url))
    result = do_write(
        ctx,
        action=f"install app from '{safe_source}'" + (" (overwrite)" if update else ""),
        audit_event={"action": "app.install", "source": safe_source, "update": update},
        run=lambda c: core.install_app(c, source, update=update),
    )
    out.emit(result, ctx.output_mode, ctx.meta())


def _safe_source(source: str, *, is_url: bool) -> str:
    """Return only the non-secret URL components used in prompts and audit records."""
    if not is_url:
        return source
    parsed = urlsplit(source)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise UsageError("--url must be an absolute http(s) URL.")
    host = parsed.hostname or ""
    try:
        port = parsed.port
    except ValueError as exc:
        raise UsageError(f"--url is invalid: {exc}") from exc
    if port is not None:
        host = f"{host}:{port}"
    return urlunsplit((parsed.scheme, host, parsed.path, "", ""))
