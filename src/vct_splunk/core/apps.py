"""App install from a local file or a URL. Click-free core.

The app CRUD surface (list/get/delete/enable/disable) is factory-generated from
the ``app`` spec. Install is the one operation that does not fit that shape, so
it lives here.

Install approach: we POST to ``/services/apps/appinstall`` with ``name=<path-or-url>``.
Splunk reads a local absolute path server-side and fetches an http(s) URL itself,
so a single form field covers both cases. This avoids a true multipart streaming
upload, which is finicky and version-dependent.

ponytail: true multipart file upload (streaming the bytes to Splunk) can be added
here when a real need appears -- e.g. installing a file the Splunk host cannot
read off its own filesystem. Today the appinstall ``name=`` form covers both
local-path and URL installs in one line.
"""

from __future__ import annotations

from typing import Any

from .client import SplunkClient

_PATH = "/services/apps/appinstall"


def install_app(client: SplunkClient, source: str, *, update: bool = False) -> dict[str, Any]:
    """Install an app from a local path or an http(s) URL.

    ``source`` is the local absolute path (``.tar.gz``/``.spl``) or the URL;
    Splunk reads it server-side. ``update=True`` allows overwriting an app that
    is already installed. This is a gated write (dry-run aware via the client).
    """
    data: dict[str, Any] = {"name": source}
    if update:
        data["update"] = "true"
    return client.write("POST", _PATH, data)
