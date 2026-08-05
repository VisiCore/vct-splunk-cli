"""Backend deduction + capability report. Click-free core (pure data).

The CLI targets two backends transparently: Splunk Enterprise (splunkd REST) and
Splunk Cloud (ACS adminconfig/v2). The backend is **deduced from SPLUNK_URL**,
never chosen by the user -- a host containing ``splunkcloud`` is Splunk Cloud
(-> ACS), anything else is Enterprise (-> splunkd REST). The user sees one flat
command surface; this module just answers "which backend is this URL, and what
can it do?" without importing Click or any client.
"""

from __future__ import annotations

import os
from typing import Any, Literal
from urllib.parse import urlsplit

Backend = Literal["enterprise", "cloud"]

_CLOUD_HOST_MARKER = "splunkcloud"

#: What each backend supports, for the `splunk inspect` report. Values are True
#: (full support) or a short string naming the limit. Cloud is read-only this
#: release. This is informational only -- routing is decided per command, and an
#: unavailable operation stops with a typed error, never a silent fallthrough.
CAPABILITIES: dict[str, dict[str, Any]] = {
    "enterprise": {
        "search": True,
        "indexes": True,
        "saved_searches": True,
        "knowledge_objects": True,
        "users_and_roles": True,
        "inputs_and_outputs": True,
        "kvstore": True,
        "apps": True,
        "health": True,
    },
    "cloud": {
        "indexes": "read-only (ACS)",
        "hec_tokens": "read-only (ACS)",
        "roles": "read-only (ACS)",
        "search": "via the search head REST (your SPLUNK_URL), where the stack permits",
        "writes": "not supported this release (read-only)",
    },
}


def _host(url: str | None) -> str:
    """Return the lowercase hostname of *url* (handles a missing scheme), or ''."""
    if not url:
        return ""
    return (urlsplit(url if "://" in url else f"//{url}").hostname or "").lower()


def deduce_backend(url: str | None = None) -> Backend:
    """Deduce the backend from a Splunk URL (``$SPLUNK_URL`` when not passed).

    A host containing ``splunkcloud`` (e.g. ``acme.splunkcloud.com``) is Splunk
    Cloud -> ACS; anything else -- including an empty or unparseable URL -- is
    Enterprise -> splunkd REST (the certified default).
    """
    raw = url if url is not None else os.environ.get("SPLUNK_URL")
    return "cloud" if _CLOUD_HOST_MARKER in _host(raw) else "enterprise"


def cloud_stack_from_url(url: str | None = None) -> str | None:
    """Derive the ACS stack from a cloud host: ``<stack>.splunkcloud.com`` -> ``<stack>``.

    Returns None for a non-cloud host. ``SPLUNK_ACS_STACK`` (if set) overrides this
    in :func:`vct_splunk.core.acs.client.acs_config_from_env`, not here.
    """
    raw = url if url is not None else os.environ.get("SPLUNK_URL")
    host = _host(raw)
    if _CLOUD_HOST_MARKER not in host:
        return None
    return host.split(".", 1)[0] or None


def inspect_report(url: str | None = None) -> dict[str, Any]:
    """Report the deduced backend and what it supports -- the ``splunk inspect`` body.

    Static and offline: it reads no live instance. The backend is deduced from the
    URL, never chosen, so a caller who explicitly asks can see which backend a
    given ``SPLUNK_URL`` resolves to and which operations exist there.
    """
    backend = deduce_backend(url)
    report: dict[str, Any] = {"backend": backend, "capabilities": CAPABILITIES[backend]}
    if backend == "cloud":
        report["stack"] = cloud_stack_from_url(url)
        report["note"] = (
            "Cloud/ACS coverage is read-only and not yet certified: the canary "
            "workflow exists, but no live Splunk Cloud stack is configured for it "
            "to run against."
        )
    return report
