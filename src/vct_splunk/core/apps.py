"""App install from a local file or a URL. Click-free core.

The app CRUD surface (list/get/delete/enable/disable) is factory-generated from
the ``app`` spec. Install is the one operation that does not fit that shape, so
it lives here.

Splunk reads the supplied server path or URL itself. This command does not upload
bytes from the caller's filesystem.
"""

from __future__ import annotations

from typing import Any

from .client import SplunkClient

_PATH = "/services/apps/local"


def install_app(
    client: SplunkClient,
    source: str,
    *,
    update: bool = False,
    preview_source: str | None = None,
) -> dict[str, Any]:
    """Install an app from a server-readable path or an http(s) URL.

    ``source`` is a server-side path (``.tar.gz``/``.spl``) or the URL;
    Splunk reads it server-side. ``preview_source`` is a sanitized equivalent
    used only in dry-run output. ``update=True`` allows overwriting an app that
    is already installed. This is a gated write (dry-run aware via the client).
    """
    display_source = (
        preview_source if client.config.dry_run and preview_source is not None else source
    )
    data: dict[str, Any] = {"name": display_source, "filename": "true"}
    if update:
        data["update"] = "true"
    return client.write("POST", _PATH, data)
