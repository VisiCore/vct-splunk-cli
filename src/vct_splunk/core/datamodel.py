"""Data model acceleration toggle. Click-free core.

Data model list/get/create/update is factory-generated from the ``datamodel``
spec. Toggling acceleration does not fit the CRUD shape and lives here.
"""

from __future__ import annotations

import json
from typing import Any

from .client import SplunkClient
from .errors import APIError, NotFoundError
from .namespace import ns_path
from .path import path_segment

_MODEL = "datamodel/model"


def accelerate(
    client: SplunkClient, name: str, *, enabled: bool, owner: str, app: str
) -> dict[str, Any]:
    """Toggle acceleration on a data model.

    Splunk replaces the model's ``acceleration`` document rather than merging
    its members. Applied writes therefore read the current document first and
    change only ``enabled``, preserving tuning such as earliest time and cron.
    Dry-runs remain request-free and preview the requested flag.
    """
    encoded = path_segment(name, label="data model name")
    path = ns_path(f"{_MODEL}/{encoded}", owner=owner, app=app)
    acceleration: dict[str, Any] = {}
    if not client.config.dry_run:
        entries = client.get(path).get("entry") or []
        if not entries:
            raise NotFoundError(f"Data model {name!r} not found.")
        raw = (entries[0].get("content") or {}).get("acceleration")
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except (TypeError, json.JSONDecodeError) as exc:
                raise APIError(
                    "Data model response contained malformed acceleration settings."
                ) from exc
        if raw is None:
            raw = {}
        if not isinstance(raw, dict):
            raise APIError("Data model response contained malformed acceleration settings.")
        acceleration = dict(raw)
    acceleration["enabled"] = enabled
    body = {"acceleration": json.dumps(acceleration, separators=(",", ":"))}
    return client.write("POST", path, body)
