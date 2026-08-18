"""Backend-transparent dispatch for the resources both backends serve. Shell layer.

A flat command (``index list``, ``role list``, ``hec-token list``) calls
:func:`dispatch_list` instead of hardcoding a client: on a deduced Cloud backend
it routes to ACS, otherwise to splunkd REST. A resource with no Cloud route stops
with a clean :class:`UnsupportedBackendError` rather than falling through to an
unofficial endpoint. This is the one place that knows both clients exist; the
Click-free core stays unaware of backends.

:func:`has_cloud_write` is the write-side counterpart, checked from
:func:`vct_splunk.commands.write.refuse_cloud_write` before a mutation ever
opens a client. The ACS write call itself
(:func:`vct_splunk.api.acs.operations.cloud_write`) is invoked directly from
:func:`vct_splunk.commands.write.do_write`, which already knows which client it
opened for the deduced backend -- there is no write-side counterpart to
``dispatch_list`` here, only the capability check.
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

_WRITE_VERBS = ("create", "update", "delete")


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
    all -- create/update/delete for index, role, and hec-token only. Every
    other Cloud mutation, including enable/disable on those same three
    resources, has none.
    """
    if resource not in acs.WRITABLE:
        return False
    return verb is None or verb in _WRITE_VERBS
