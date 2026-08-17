"""ACS operations: unrestricted reads plus the three writable resources.

Only index, role, and HTTP Event Collector token support create/update/delete
on Splunk Cloud (see ``WRITE_PATHS``, checked against Splunk's public OpenAPI by
``tests/integration/test_acs_public_spec.py``). Every write goes through
:meth:`~vct_splunk.api.acs.client.AcsClient.write`, so ``--dry-run`` sends
nothing here exactly as it does for the Enterprise REST path; the opt-in gate
and the allowlist of which (resource, verb) pairs even reach these functions
live one layer up, in :mod:`vct_splunk.commands.write` and
:mod:`vct_splunk.commands.dispatch`.
"""

from __future__ import annotations

from typing import Any

from ...utils.errors import APIError
from ...utils.path import path_segment
from ...utils.redact import redact_secrets
from .client import AcsClient

# ACS read paths and their official success envelopes. This is the runtime
# declaration used by both the client and the credential-free contract test.
INDEXES = "indexes"
HEC_TOKENS = "inputs/http-event-collectors"
ROLES = "roles"

LIST_ENVELOPES = {
    INDEXES: "indexes",
    HEC_TOKENS: "http_event_collectors",
    ROLES: "roles",
}

#: Every ACS path the CLI reads.
READ_PATHS = tuple(LIST_ENVELOPES)

#: (path template, HTTP method) pairs ACS exposes for create/update/delete on
#: the three writable resources. Templates use Splunk's own OpenAPI
#: path-parameter names, so the public-spec drift check
#: (``tests/integration/test_acs_public_spec.py``) can look each one up
#: directly against the published contract; the functions below build the real
#: request path with an actual name instead of the placeholder.
WRITE_PATHS: tuple[tuple[str, str], ...] = (
    (INDEXES, "post"),
    (f"{INDEXES}/{{index}}", "patch"),
    (f"{INDEXES}/{{index}}", "delete"),
    (ROLES, "post"),
    (f"{ROLES}/{{roleName}}", "patch"),
    (f"{ROLES}/{{roleName}}", "delete"),
    (HEC_TOKENS, "post"),
    (f"{HEC_TOKENS}/{{hec}}", "patch"),
    (f"{HEC_TOKENS}/{{hec}}", "delete"),
)


def list_cloud_indexes(client: AcsClient) -> list[dict[str, Any]]:
    """List indexes on the Cloud stack (ACS)."""
    return _list(client, INDEXES, LIST_ENVELOPES[INDEXES])


def list_hec_tokens(client: AcsClient) -> list[dict[str, Any]]:
    """List HTTP Event Collector tokens on the Cloud stack (ACS)."""
    return _list(client, HEC_TOKENS, LIST_ENVELOPES[HEC_TOKENS])


def list_cloud_roles(client: AcsClient) -> list[dict[str, Any]]:
    """List roles on the Cloud stack (ACS)."""
    return _list(client, ROLES, LIST_ENVELOPES[ROLES])


def _list(client: AcsClient, path: str, envelope: str) -> list[dict[str, Any]]:
    """Read every page from one official ACS list envelope, minus any secrets.

    Token stripping happens here rather than in the one operation whose payload
    is known to carry a secret today. Redacting at the boundary means no ACS
    read can return a token, including one Splunk adds to an endpoint later.
    """
    output: list[dict[str, Any]] = []
    offset = 0
    while True:
        body = client.get(path, {"count": 100, "offset": offset})
        if not isinstance(body, dict) or not isinstance(body.get(envelope), list):
            raise APIError(f"ACS response is missing the {envelope!r} list envelope.")
        page = body[envelope]
        if not all(isinstance(item, dict) for item in page):
            raise APIError(f"ACS response contains malformed items in {envelope!r}.")
        output.extend(redact_secrets(item) for item in page)
        if len(page) < 100:
            return output
        offset += len(page)


def create_cloud_index(client: AcsClient, name: str, body: dict[str, Any]) -> Any:
    """Create an index on the Cloud stack (ACS). Splunk provisions it asynchronously."""
    return _write(client, "POST", INDEXES, {**body, "name": name})


def update_cloud_index(client: AcsClient, name: str, body: dict[str, Any]) -> Any:
    """Update an index's settings on the Cloud stack (ACS)."""
    return _write(client, "PATCH", f"{INDEXES}/{_encoded(name)}", body)


def delete_cloud_index(client: AcsClient, name: str, body: dict[str, Any] | None = None) -> Any:
    """Delete an index on the Cloud stack (ACS). Deletion completes asynchronously."""
    return _write(client, "DELETE", f"{INDEXES}/{_encoded(name)}", body or {})


def create_cloud_role(client: AcsClient, name: str, body: dict[str, Any]) -> Any:
    """Create a role on the Cloud stack (ACS)."""
    return _write(client, "POST", ROLES, {**body, "name": name})


def update_cloud_role(client: AcsClient, name: str, body: dict[str, Any]) -> Any:
    """Update a role's settings on the Cloud stack (ACS)."""
    return _write(client, "PATCH", f"{ROLES}/{_encoded(name)}", body)


def delete_cloud_role(client: AcsClient, name: str, body: dict[str, Any] | None = None) -> Any:
    """Delete a role on the Cloud stack (ACS)."""
    return _write(client, "DELETE", f"{ROLES}/{_encoded(name)}", body or {})


def create_hec_token(client: AcsClient, name: str, body: dict[str, Any]) -> Any:
    """Create an HTTP Event Collector token on the Cloud stack (ACS).

    Unlike the Enterprise ``hec-token create`` (whose response is allowed to
    reveal the token because it is the only way to learn it), the ACS response
    is redacted here like every other ACS write. Splunk Cloud CI output must
    never carry a live credential, so there is no reveal-once escape hatch on
    this path.
    """
    return _write(client, "POST", HEC_TOKENS, {**body, "name": name})


def update_hec_token(client: AcsClient, name: str, body: dict[str, Any]) -> Any:
    """Update an HTTP Event Collector token's settings on the Cloud stack (ACS)."""
    return _write(client, "PATCH", f"{HEC_TOKENS}/{_encoded(name)}", body)


def delete_hec_token(client: AcsClient, name: str, body: dict[str, Any] | None = None) -> Any:
    """Delete an HTTP Event Collector token on the Cloud stack (ACS)."""
    return _write(client, "DELETE", f"{HEC_TOKENS}/{_encoded(name)}", body or {})


def _encoded(name: str) -> str:
    """Validate and percent-encode a name for use in an ACS item path."""
    return path_segment(name, label="name")


def _write(client: AcsClient, method: str, path: str, body: dict[str, Any]) -> Any:
    """Send one ACS mutation and redact any secret before it reaches the caller.

    A dry-run preview (``{"dry_run": True, ...}``) carries no live data and
    passes through unredacted, same as :meth:`~vct_splunk.api.client.SplunkClient.write`.
    """
    result = client.write(method, path, body)
    if isinstance(result, dict) and result.get("dry_run"):
        return result
    return redact_secrets(result)
