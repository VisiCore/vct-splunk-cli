"""Data model acceleration toggle. Click-free core.

Data model list/get/create/update is factory-generated from the ``datamodel``
spec. Toggling acceleration does not fit the CRUD shape and lives here.
"""

from __future__ import annotations

from typing import Any

from .client import SplunkClient
from .namespace import ns_path
from .path import path_segment

_MODEL = "datamodel/model"


def accelerate(
    client: SplunkClient, name: str, *, enabled: bool, owner: str, app: str
) -> dict[str, Any]:
    """Toggle acceleration on a data model.

    Posts to the model stanza with an ``acceleration`` JSON field carrying
    ``{"enabled": true|false}``. Splunk merges this into the model's
    acceleration settings; only the ``enabled`` flag is changed.

    ponytail: we send only ``acceleration={"enabled": ...}`` to the model
    endpoint -- the simplest form Splunk accepts. Other acceleration knobs
    (earliest time, cron) are reachable via ``datamodel update --set`` and are
    not modeled here until a real need appears.
    """
    flag = "true" if enabled else "false"
    body = {"acceleration": f'{{"enabled": {flag}}}'}
    encoded = path_segment(name, label="data model name")
    return client.write("POST", ns_path(f"{_MODEL}/{encoded}", owner=owner, app=app), body)
