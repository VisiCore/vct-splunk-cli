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


def install_app(client: SplunkClient, source: str, *, update: bool = False) -> dict[str, Any]:
    """Install an app from a server-readable path or an http(s) URL.

    ``source`` is a server-side path (``.tar.gz``/``.spl``) or the URL;
    Splunk reads it server-side. ``update=True`` allows overwriting an app that
    is already installed. This is a gated write (dry-run aware via the client).
    """
    data: dict[str, Any] = {"name": source}
    if update:
        data["update"] = "true"
    return client.write("POST", _PATH, data)
