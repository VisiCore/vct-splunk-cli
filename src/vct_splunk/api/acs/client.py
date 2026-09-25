"""A thin client for the Splunk Cloud ACS adminconfig/v2 API.

ACS is a different surface from splunkd: a different base URL
(``https://admin.splunk.com/<stack>/adminconfig/v2``), a stack auth token, and
plain JSON responses (not the form-encoded ``entry[].content`` shape). So it gets
its own small client rather than reusing :class:`~vct_splunk.api.client.SplunkClient`.

Reads (:meth:`get`) are unrestricted. Mutations (:meth:`write`) exist too, but
this client sends whatever it is told -- the opt-in gate and the allowlist of
which (resource, verb) pairs are ever reachable live one layer up, in
:mod:`vct_splunk.commands.write` and :mod:`vct_splunk.commands.dispatch`.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx

from ...utils.errors import APIError, AuthError, NotFoundError, TransportError, UsageError
from ...utils.redact import public_target, redact_exception_text

ACS_BASE_URL = "https://admin.splunk.com"
_STACK_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*$")
_MAX_RETRIES = 3


@dataclass
class AcsConfig:
    stack: str
    token: str
    base_url: str = ACS_BASE_URL
    timeout: float = 30.0
    dry_run: bool = False


def acs_config_from_env(stack: str | None = None, *, write: bool = False) -> AcsConfig:
    """Build an ACS config: the stack (derived from SPLUNK_URL) + an ACS token.

    The Cloud stack is normally derived from the ``*.splunkcloud.com`` host in
    ``SPLUNK_URL`` and passed in as ``stack``; ``SPLUNK_ACS_STACK`` is a rare
    explicit override.

    Args:
        stack: The Cloud stack name, or None to require ``SPLUNK_ACS_STACK``.
        write: When True, prefer ``SPLUNK_ACS_WRITE_TOKEN`` (falling back to
            ``SPLUNK_ACS_TOKEN`` when unset) -- lets an operator scope a
            write-capable token separately from the read token. Reads always
            use ``SPLUNK_ACS_TOKEN`` only, never the write token.
    """
    stack = os.environ.get("SPLUNK_ACS_STACK") or stack
    token = os.environ.get("SPLUNK_ACS_TOKEN")
    if write:
        token = os.environ.get("SPLUNK_ACS_WRITE_TOKEN") or token
    if not stack:
        raise UsageError(
            "Could not determine the Splunk Cloud stack. Set SPLUNK_URL to your "
            "https://<stack>.splunkcloud.com host (or set SPLUNK_ACS_STACK)."
        )
    if not token:
        env_name = "SPLUNK_ACS_WRITE_TOKEN or SPLUNK_ACS_TOKEN" if write else "SPLUNK_ACS_TOKEN"
        raise UsageError(f"No ACS token. Set {env_name} for Splunk Cloud operations.")
    if not _STACK_RE.fullmatch(stack):
        raise UsageError(
            "Invalid ACS stack name. Use only letters, numbers, and hyphens, "
            "starting with a letter or number."
        )
    base_url = (os.environ.get("SPLUNK_ACS_BASE_URL") or ACS_BASE_URL).rstrip("/")
    return AcsConfig(stack=stack, token=token, base_url=base_url)


class AcsClient:
    """Access to one Splunk Cloud stack's ACS adminconfig/v2 API.

    Reads (:meth:`get`) are unrestricted. Mutations (:meth:`write`) are dry-run
    gated the same way :meth:`vct_splunk.api.client.SplunkClient.write` is --
    ``config.dry_run`` sends nothing and returns a preview instead. This client
    does not itself decide *which* resources may be written or whether the
    caller opted in; that gate is one layer up, in
    :func:`vct_splunk.commands.write.refuse_cloud_write`.
    """

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
        return self.request("GET", path, params=params)

    def write(self, method: str, path: str, json_body: Any | None = None) -> Any:
        """Mutating ACS request. When dry_run is set, sends nothing and returns a preview.

        Mirrors :meth:`vct_splunk.api.client.SplunkClient.write`: the caller (an
        ACS operation function) is trusted to have already decided this mutation
        is allowed to run; this method only decides whether to send it.
        """
        if self.config.dry_run:
            base = f"{self.config.base_url}/{self.config.stack}/adminconfig/v2"
            return {
                "dry_run": True,
                "request": {"method": method, "path": "/" + path.lstrip("/"), "body": json_body},
                "target": public_target(base),
            }
        return self.request(method, path, json_body=json_body)

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any | None = None,
    ) -> Any:
        """Send one ACS request and return the parsed JSON response.

        Shared by every read and (non-dry-run) write: retries 429/5xx honoring
        ``Retry-After``, and maps status codes to the same typed errors GET has
        always raised.
        """
        url = "/" + path.lstrip("/")
        for attempt in range(_MAX_RETRIES + 1):
            try:
                resp = self._http.request(method, url, params=params, json=json_body)
            except httpx.HTTPError as exc:
                raise TransportError(
                    f"Could not reach ACS at {public_target(self.config.base_url)}: "
                    f"{redact_exception_text(str(exc))}"
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
                raise APIError(f"ACS returned {resp.status_code} for {method} {url}")
            if not resp.content:
                return {}
            try:
                return resp.json()
            except ValueError as exc:
                raise APIError(f"ACS returned malformed JSON for {method} {url}") from exc
        raise TransportError("ACS retries exhausted")  # pragma: no cover


def _retry_after(resp: httpx.Response, attempt: int) -> float:
    value = resp.headers.get("Retry-After")
    if value and value.isdigit():
        return float(value)
    return min(2.0**attempt, 8.0)
