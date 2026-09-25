"""ACS operations: unrestricted reads plus the three writable resources.

Only index, role, and HTTP Event Collector token support create/update/delete
on Splunk Cloud (see :data:`WRITABLE`, checked against Splunk's public OpenAPI
by ``tests/integration/test_acs_public_spec.py`` via :data:`WRITE_PATHS`).
Every write goes through :meth:`~vct_splunk.api.acs.client.AcsClient.write`,
so ``--dry-run`` sends nothing here exactly as it does for the Enterprise REST
path; the opt-in gate and the allowlist of which (resource, verb) pairs even
reach :func:`cloud_write` live one layer up, in
:mod:`vct_splunk.commands.write` and :mod:`vct_splunk.commands.dispatch`.
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

#: CLI resource name -> (ACS collection path, Splunk's own OpenAPI
#: path-parameter name for one item). The parameter name differs per resource
#: (`{index}`, `{roleName}`, `{hec}`), so :data:`WRITE_PATHS` below carries it
#: rather than a generic placeholder -- the spec drift check looks paths up
#: verbatim in Splunk's published contract.
WRITABLE: dict[str, tuple[str, str]] = {
    "index": (INDEXES, "index"),
    "role": (ROLES, "roleName"),
    "hec-token": (HEC_TOKENS, "hec"),
}

#: (path template, HTTP method) pairs ACS exposes for create/update/delete on
#: the three writable resources, derived from :data:`WRITABLE` so this and
#: :func:`cloud_write` can never drift apart.
WRITE_PATHS: tuple[tuple[str, str], ...] = tuple(
    (path, method)
    for base, param in WRITABLE.values()
    for path, method in (
        (base, "post"),
        (f"{base}/{{{param}}}", "patch"),
        (f"{base}/{{{param}}}", "delete"),
    )
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


def cloud_write(
    client: AcsClient, resource: str, verb: str, name: str, body: dict[str, Any] | None = None
) -> Any:
    """Create, update, or delete one object of a Cloud-writable resource via ACS.

    ``resource`` must be a key of :data:`WRITABLE` and ``verb`` one of
    create/update/delete -- the caller
    (:func:`vct_splunk.commands.dispatch.dispatch_write`) has already checked
    both against the same allowlist this reads, so a `KeyError` here would
    mean that check was bypassed.

    Unlike the Enterprise ``hec-token create`` (whose response is allowed to
    reveal the minted token because it is the only way to learn it), every ACS
    write response is redacted here -- Splunk Cloud CI output must never carry
    a live credential, so there is no reveal-once escape hatch on this path.
    """
    collection, _ = WRITABLE[resource]
    if verb == "create":
        result = client.write("POST", collection, {**(body or {}), "name": name})
    else:
        path = f"{collection}/{path_segment(name, label='name')}"
        method = "PATCH" if verb == "update" else "DELETE"
        result = client.write(method, path, body or {})
    if isinstance(result, dict) and result.get("dry_run"):
        return result
    return redact_secrets(result)
