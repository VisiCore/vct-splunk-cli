"""Read Splunk configuration files and stanzas. Click-free core."""

from __future__ import annotations

from typing import Any

from .client import SplunkClient
from .namespace import ns_path
from .path import path_segment
from .redact import REDACTED, is_secret_key, redact_secrets


def list_files(client: SplunkClient, *, owner: str, app: str) -> list[dict[str, Any]]:
    """Return configuration files visible in one Splunk namespace."""
    path = ns_path("properties", owner=owner, app=app)
    return [_name(entry) for entry in client.get_collection(path)]


def list_stanzas(client: SplunkClient, file: str, *, owner: str, app: str) -> list[dict[str, Any]]:
    """Return every stanza in a visible configuration file."""
    path = _base(file, owner=owner, app=app)
    return [_name(entry) for entry in client.get_collection(path)]


def get_stanza(
    client: SplunkClient, file: str, stanza: str, *, owner: str, app: str
) -> dict[str, Any]:
    """Return the properties in one visible configuration stanza."""
    encoded_stanza = path_segment(stanza, label="configuration stanza")
    path = f"{_base(file, owner=owner, app=app)}/{encoded_stanza}"
    properties: dict[str, Any] = {}
    for entry in client.get_collection(path):
        name = str(entry.get("name"))
        content = entry.get("content")
        properties[name] = REDACTED if is_secret_key(name) else redact_secrets(content)
    return {"name": stanza, "properties": properties}


def _base(file: str, *, owner: str, app: str) -> str:
    """Build a namespace-qualified configuration-file endpoint."""
    return f"{ns_path('properties', owner=owner, app=app)}/{_normal_file(file)}"


def _normal_file(file: str) -> str:
    """Validate and encode a config-file name, accepting one optional .conf suffix."""
    name = file[:-5] if file.endswith(".conf") else file
    return path_segment(name, label="configuration file")


def _name(entry: dict[str, Any]) -> dict[str, Any]:
    """Return only the authoritative REST entry name for a file or stanza listing."""
    return {"name": entry.get("name")}
