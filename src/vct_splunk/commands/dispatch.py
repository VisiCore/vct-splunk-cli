"""Backend-transparent dispatch for the resources both backends serve. Shell layer.

A flat command (``index list``, ``role list``, ``hec-token list``) calls
:func:`dispatch_list` instead of hardcoding a client: on a deduced Cloud backend
it routes to ACS, otherwise to splunkd REST. A resource with no Cloud route stops
with a clean :class:`UnsupportedBackendError` rather than falling through to an
unofficial endpoint. This is the one place that knows both clients exist; the
Click-free core stays unaware of backends.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..core.acs import operations as acs
from ..core.errors import UnsupportedBackendError

#: resource name -> the ACS read op. Only these resources have a Cloud route; the
#: REST side is supplied by each call site (it already knows its own path/output).
_ACS_LIST: dict[str, Callable[[Any], Any]] = {
    "index": acs.list_cloud_indexes,
    "role": acs.list_cloud_roles,
    "hec-token": acs.list_hec_tokens,
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
