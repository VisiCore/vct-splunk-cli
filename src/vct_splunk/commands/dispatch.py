"""Backend-transparent dispatch for the resources both backends serve. Shell layer.

A flat command (``index list``, ``role list``, ``hec-token list``) calls
:func:`dispatch_list` instead of hardcoding a client: on a deduced Cloud backend
it routes to ACS, otherwise to splunkd REST. A resource with no Cloud route stops
with a clean :class:`UnsupportedBackendError` rather than falling through to an
unofficial endpoint. This is the one place that knows both clients exist; the
Click-free core stays unaware of backends.

:func:`dispatch_write` is the write-side counterpart, used from inside
:func:`vct_splunk.commands.write.do_write`'s gated ``run`` callback. Cloud writes
are opt-in and narrow (see that module for the gate); this module only knows
*which* (resource, verb) pairs have an ACS route at all.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..api.acs import operations as acs
from ..utils.errors import UnsupportedBackendError

#: resource name -> the ACS read op. Only these resources have a Cloud route; the
#: REST side is supplied by each call site (it already knows its own path/output).
_ACS_LIST: dict[str, Callable[[Any], Any]] = {
    "index": acs.list_cloud_indexes,
    "role": acs.list_cloud_roles,
    "hec-token": acs.list_hec_tokens,
}

#: (resource, verb) -> the ACS op, called as ``op(client, name, body)``. Only
#: create/update/delete for these three resources have a Cloud write route;
#: every other resource, and enable/disable on these same three, has none.
_ACS_WRITE: dict[tuple[str, str], Callable[[Any, str, dict[str, Any]], Any]] = {
    ("index", "create"): acs.create_cloud_index,
    ("index", "update"): acs.update_cloud_index,
    ("index", "delete"): acs.delete_cloud_index,
    ("role", "create"): acs.create_cloud_role,
    ("role", "update"): acs.update_cloud_role,
    ("role", "delete"): acs.delete_cloud_role,
    ("hec-token", "create"): acs.create_hec_token,
    ("hec-token", "update"): acs.update_hec_token,
    ("hec-token", "delete"): acs.delete_hec_token,
}


def has_cloud_list(resource: str) -> bool:
    """True if ``resource``'s list is served by ACS on the Cloud backend."""
    return resource in _ACS_LIST


def dispatch_list(ctx: Any, resource: str, rest_call: Callable[[Any], Any]) -> Any:
    """Run ``resource`` list against the deduced backend: ACS on Cloud, REST otherwise.

    ``rest_call`` is the Enterprise path (given an open ``SplunkClient``). On Cloud
    we ignore it and call the matching ACS op via ``ctx.acs_client()``; a resource
    with no Cloud route raises :class:`UnsupportedBackendError`.
    """
    if ctx.backend == "cloud":
        op = _ACS_LIST.get(resource)
        if op is None:
            raise UnsupportedBackendError(resource, "list", "cloud")
        with ctx.acs_client() as c:
            return op(c)
    with ctx.client() as c:
        return rest_call(c)


def has_cloud_write(resource: str, verb: str | None = None) -> bool:
    """True if ``(resource, verb)`` is a Cloud-writable mutation via ACS.

    With ``verb`` omitted, true if ``resource`` has any Cloud write route at
    all (used where only the resource is known yet, e.g. before a verb-specific
    check runs).
    """
    if verb is None:
        return any(r == resource for r, _ in _ACS_WRITE)
    return (resource, verb) in _ACS_WRITE


def dispatch_write(
    ctx: Any,
    resource: str,
    verb: str,
    name: str,
    client: Any,
    rest_call: Callable[[Any], Any],
    *,
    body: dict[str, Any] | None = None,
) -> Any:
    """Run one write against the deduced backend: ACS on Cloud, REST otherwise.

    Called from inside :func:`vct_splunk.commands.write.do_write`'s gated
    ``run`` callback, with the client it already opened for this backend (an
    ``AcsClient`` on Cloud, a ``SplunkClient`` otherwise) -- no client is opened
    here. ``do_write`` has already refused a Cloud write whose ``(resource,
    verb)`` has no ACS route (see ``refuse_cloud_write``), so a lookup miss here
    would mean that gate was bypassed.
    """
    if ctx.backend == "cloud":
        op = _ACS_WRITE[(resource, verb)]
        return op(client, name, body or {})
    return rest_call(client)
