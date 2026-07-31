"""A thin, read-only client for the Splunk Cloud ACS adminconfig/v2 API.

ACS is a different surface from splunkd: a different base URL
(``https://admin.splunk.com/<stack>/adminconfig/v2``), a stack auth token, and
plain JSON responses (not the form-encoded ``entry[].content`` shape). So it gets
its own small client rather than reusing :class:`~vct_splunk.core.client.SplunkClient`.
Writes are intentionally absent this release.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx

from ..errors import APIError, AuthError, NotFoundError, TransportError, UsageError

ACS_BASE_URL = "https://admin.splunk.com"
_STACK_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*$")
_MAX_RETRIES = 3


@dataclass
class AcsConfig:
    stack: str
    token: str
    base_url: str = ACS_BASE_URL
    timeout: float = 30.0


def acs_config_from_env(stack: str | None = None) -> AcsConfig:
    """Build an ACS config: the stack (derived from SPLUNK_URL) + ``SPLUNK_ACS_TOKEN``.

    The Cloud stack is normally derived from the ``*.splunkcloud.com`` host in
    ``SPLUNK_URL`` and passed in as ``stack``; ``SPLUNK_ACS_STACK`` is a rare
    explicit override. ``SPLUNK_ACS_TOKEN`` (a Bearer token, separate from the
    Enterprise auth token) is always required for ACS operations.
    """
    stack = os.environ.get("SPLUNK_ACS_STACK") or stack
    token = os.environ.get("SPLUNK_ACS_TOKEN")
    if not stack:
        raise UsageError(
            "Could not determine the Splunk Cloud stack. Set SPLUNK_URL to your "
            "https://<stack>.splunkcloud.com host (or set SPLUNK_ACS_STACK)."
        )
    if not token:
        raise UsageError("No ACS token. Set SPLUNK_ACS_TOKEN for Splunk Cloud operations.")
    if not _STACK_RE.fullmatch(stack):
        raise UsageError(
            "Invalid ACS stack name. Use only letters, numbers, and hyphens, "
            "starting with a letter or number."
        )
    base_url = os.environ.get("SPLUNK_ACS_BASE_URL", ACS_BASE_URL).rstrip("/")
    return AcsConfig(stack=stack, token=token, base_url=base_url)


class AcsClient:
    """Read-only GET access to one Splunk Cloud stack's ACS adminconfig/v2 API."""

    def __init__(self, config: AcsConfig, *, transport: httpx.BaseTransport | None = None) -> None:
        if not _STACK_RE.fullmatch(config.stack):
            raise UsageError("Invalid ACS stack name.")
        self.config = config
        self._http = httpx.Client(
            base_url=f"{config.base_url}/{config.stack}/adminconfig/v2",
            headers={"Authorization": f"Bearer {config.token}", "Accept": "application/json"},
            timeout=config.timeout,
            transport=transport,
        )

    def __enter__(self) -> AcsClient:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self._http.close()

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """GET an ACS read endpoint and return the parsed JSON."""
        url = "/" + path.lstrip("/")
        for attempt in range(_MAX_RETRIES + 1):
            try:
                resp = self._http.get(url, params=params)
            except httpx.HTTPError as exc:
                raise TransportError(
                    f"Could not reach ACS at {self.config.base_url}: {exc}"
                ) from exc
            if (resp.status_code == 429 or 500 <= resp.status_code < 600) and (
                attempt < _MAX_RETRIES
            ):
                time.sleep(_retry_after(resp, attempt))
                continue
            if resp.status_code in (401, 403):
                raise AuthError(f"ACS auth failed ({resp.status_code}). Check SPLUNK_ACS_TOKEN.")
            if resp.status_code == 404:
                raise NotFoundError(f"ACS endpoint not found: {url}")
            if resp.status_code >= 400:
                raise APIError(f"ACS returned {resp.status_code} for GET {url}")
            if not resp.content:
                return {}
            try:
                return resp.json()
            except ValueError as exc:
                raise APIError(f"ACS returned malformed JSON for GET {url}") from exc
        raise TransportError("ACS retries exhausted")  # pragma: no cover


def _retry_after(resp: httpx.Response, attempt: int) -> float:
    value = resp.headers.get("Retry-After")
    if value and value.isdigit():
        return float(value)
    return min(2.0**attempt, 8.0)
