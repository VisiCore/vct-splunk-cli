"""Read-only ACS operations. The path constants are pinned against the vendored
OpenAPI subset (a contract test asserts each one exists in that spec)."""

from __future__ import annotations

from typing import Any

from ..errors import APIError
from .client import AcsClient

# ACS read paths used by this CLI. Keep in sync with openapi/adminconfig-v2.json
# (the contract test enforces it).
INDEXES = "indexes"
HEC_TOKENS = "inputs/http-event-collectors"
ROLES = "roles"

#: Every ACS path the CLI reads -- the contract test checks these are in the spec.
READ_PATHS = (INDEXES, HEC_TOKENS, ROLES)


def list_cloud_indexes(client: AcsClient) -> list[dict[str, Any]]:
    """List indexes on the Cloud stack (ACS)."""
    return _list(client, INDEXES, "indexes")


def list_hec_tokens(client: AcsClient) -> list[dict[str, Any]]:
    """List HTTP Event Collector tokens on the Cloud stack (ACS)."""
    return [_without_tokens(item) for item in _list(client, HEC_TOKENS, "http_event_collectors")]


def list_cloud_roles(client: AcsClient) -> list[dict[str, Any]]:
    """List roles on the Cloud stack (ACS)."""
    return _list(client, ROLES, "roles")


def _list(client: AcsClient, path: str, envelope: str) -> list[dict[str, Any]]:
    """Read every page from one official ACS list envelope."""
    output: list[dict[str, Any]] = []
    offset = 0
    while True:
        body = client.get(path, {"count": 100, "offset": offset})
        if not isinstance(body, dict) or not isinstance(body.get(envelope), list):
            raise APIError(f"ACS response is missing the {envelope!r} list envelope.")
        page = body[envelope]
        if not all(isinstance(item, dict) for item in page):
            raise APIError(f"ACS response contains malformed items in {envelope!r}.")
        output.extend(page)
        if len(page) < 100:
            return output
        offset += len(page)


def _without_tokens(value: Any) -> Any:
    """Remove token fields before HEC data leaves the ACS operation boundary."""
    if isinstance(value, dict):
        return {
            key: _without_tokens(item) for key, item in value.items() if key.casefold() != "token"
        }
    if isinstance(value, list):
        return [_without_tokens(item) for item in value]
    return value
