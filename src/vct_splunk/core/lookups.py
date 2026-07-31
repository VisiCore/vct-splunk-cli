"""Lookup table file upload. Click-free core.

Lookup *definitions* (the transforms.conf stanza) are factory-generated from the
``lookup-definition`` spec. Uploading the CSV table file itself is a namespaced
write that does not fit the CRUD shape and lives here.
"""

from __future__ import annotations

from typing import Any

from .client import SplunkClient
from .namespace import ns_path

_FILES = "data/lookup-table-files"


def upload_lookup(
    client: SplunkClient, filename: str, server_file: str, *, owner: str, app: str
) -> dict[str, Any]:
    """Create a lookup-table file entry from a path readable by splunkd.

    ``filename`` is the name the table file will have in the app.
    ``server_file`` is the staging path on the Splunk server.
    """
    body: dict[str, Any] = {"name": filename, "eai:data": server_file}
    return client.write("POST", ns_path(_FILES, owner=owner, app=app), body)
