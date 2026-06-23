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
    client: SplunkClient, filename: str, contents: str, *, owner: str, app: str
) -> dict[str, Any]:
    """Create a lookup-table file entry, sending the CSV bytes as ``eai:data``.

    Splunk's lookup-table-files endpoint accepts the file name plus the file
    body as the ``eai:data`` form field, which avoids a true multipart upload.
    ``filename`` is the name the table file will have in the app; ``contents``
    is the raw CSV text read from the local path by the command layer.

    ponytail: this sends the whole CSV inline as a form field, which is fine for
    typical lookup tables. Streaming a multi-hundred-MB file would need a real
    multipart helper on the client -- not built until a large file appears.
    """
    body: dict[str, Any] = {"name": filename, "eai:data": contents}
    return client.write("POST", ns_path(_FILES, owner=owner, app=app), body)
