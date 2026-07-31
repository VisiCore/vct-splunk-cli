"""HTTP Event Collector (HEC) extras that the CRUD factory cannot express.

The HEC *token* list/get/create/update/delete surface is factory-generated from
the ``hec-token`` spec. Two operations do not fit that CRUD shape and live here:

* token rotation -- minting a fresh token value for an existing stanza, and
* the global HEC input toggle (``http``) that enables/disables HEC as a whole.

This is Click-free core: plain functions taking a :class:`SplunkClient`.
"""

from __future__ import annotations

from typing import Any

from .client import SplunkClient
from .errors import APIError
from .path import path_segment

_HTTP = "/services/data/inputs/http"


def rotate_token(client: SplunkClient, name: str) -> dict[str, Any]:
    """Regenerate the secret of an existing HEC token, returning the new value.

    The new token is returned to the caller but must never be written to the
    audit log.
    """
    encoded = path_segment(name, label="HEC token name")
    result = client.write("POST", f"{_HTTP}/{encoded}/rotate", {})
    if result.get("dry_run"):
        return result
    entries = result.get("entry") or []
    content = entries[0].get("content") if entries else {}
    token = (content or {}).get("token")
    if not token:
        raise APIError("Splunk's HEC rotation response did not contain a new token.")
    return {"name": name, "token": token}


def set_global(client: SplunkClient, *, enabled: bool) -> dict[str, Any]:
    """Enable or disable HEC globally via the ``http`` input stanza.

    The global HEC listener is the special ``http`` stanza (not a token). A POST
    with ``disabled=0`` turns the collector on; ``disabled=1`` turns it off.
    """
    disabled = 0 if enabled else 1
    return client.write("POST", f"{_HTTP}/http", {"disabled": disabled})
