"""Read-only ACS operations. The path constants are pinned against the vendored
OpenAPI subset (a contract test asserts each one exists in that spec)."""

from __future__ import annotations

from typing import Any

from .client import AcsClient

# ACS read paths used by this CLI. Keep in sync with openapi/adminconfig-v2.json
# (the contract test enforces it).
INDEXES = "indexes"
HEC_TOKENS = "inputs/http-event-collectors"
ROLES = "roles"

#: Every ACS path the CLI reads -- the contract test checks these are in the spec.
READ_PATHS = (INDEXES, HEC_TOKENS, ROLES)


def list_cloud_indexes(client: AcsClient) -> Any:
    """List indexes on the Cloud stack (ACS)."""
    return client.get(INDEXES)


def list_hec_tokens(client: AcsClient) -> Any:
    """List HTTP Event Collector tokens on the Cloud stack (ACS)."""
    return client.get(HEC_TOKENS)


def list_cloud_roles(client: AcsClient) -> Any:
    """List roles on the Cloud stack (ACS)."""
    return client.get(ROLES)
