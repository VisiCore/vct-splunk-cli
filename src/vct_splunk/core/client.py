"""Splunk REST client: auth, TLS, retries, pagination, dry-run. Click-free core.

One place owns transport concerns so every command behaves consistently. The auth
token lives only in a header (never logged); mutating requests are suppressed (and
previewed) when ``dry_run`` is set.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

import httpx

from .errors import APIError, AuthError, NotFoundError, TransportError, UsageError

_RETRY_STATUS = {429, 503}
_MAX_RETRIES = 3


@dataclass
class ClientConfig:
    base_url: str
    token: str
    verify: bool | str = True  # True/False, or a path to a CA bundle
    timeout: float = 30.0
    dry_run: bool = False
    # Splunk accepts a JWT as "Bearer <token>" or a session key as "Splunk <sessionKey>".
    auth_scheme: str = "Bearer"


def _login(base_url: str, username: str, password: str, verify: bool | str) -> str:
    """Exchange a username and password for a Splunk session key.

    POSTs to ``/services/auth/login`` and returns the ``sessionKey``. This is a
    last-resort path (mainly for CI); username/password is not the encouraged way
    to authenticate. The password lives only in this request body, never logged.
    """
    try:
        resp = httpx.post(
            f"{base_url}/services/auth/login",
            data={"username": username, "password": password, "output_mode": "json"},
            verify=verify,
            timeout=30.0,
        )
    except httpx.HTTPError as exc:
        raise TransportError(f"Could not reach Splunk at {base_url}: {exc}") from exc
    if resp.status_code in {401, 403}:
        raise AuthError("Splunk rejected the username and password.")
    if resp.status_code >= 400:
        raise APIError(f"Splunk login failed ({resp.status_code}).", details=resp.text)
    key = resp.json().get("sessionKey")
    if not key:
        raise AuthError("Splunk login returned no session key.")
    return key


def config_from_env(base_url: str | None = None) -> ClientConfig:
    url = base_url or os.environ.get("SPLUNK_URL")
    if not url:
        raise UsageError("No Splunk URL. Set SPLUNK_URL or pass --base-url.")
    url = url.rstrip("/")
    ca = os.environ.get("SPLUNK_CA_BUNDLE")
    verify = ca or (
        os.environ.get("SPLUNK_VERIFY", "true").strip().lower() not in {"0", "false", "no"}
    )
    # A JWT (SPLUNK_TOKEN) is the primary path and takes precedence; a session key
    # (SPLUNK_SESSION_KEY) is the simple alternative. As a last resort the client logs
    # in with SPLUNK_USERNAME/SPLUNK_PASSWORD to get a session key itself -- handy for
    # CI, but not a documented or encouraged way to authenticate.
    token = os.environ.get("SPLUNK_TOKEN")
    if token:
        scheme, credential = "Bearer", token
    elif session_key := os.environ.get("SPLUNK_SESSION_KEY"):
        scheme, credential = "Splunk", session_key
    elif (username := os.environ.get("SPLUNK_USERNAME")) and (
        password := os.environ.get("SPLUNK_PASSWORD")
    ):
        scheme, credential = "Splunk", _login(url, username, password, verify)
    else:
        raise UsageError(
            "No auth. Set SPLUNK_TOKEN (a JWT) or SPLUNK_SESSION_KEY "
            "(a session key from /services/auth/login)."
        )
    return ClientConfig(base_url=url, token=credential, verify=verify, auth_scheme=scheme)


class SplunkClient:
    def __init__(
        self, config: ClientConfig, *, transport: httpx.BaseTransport | None = None
    ) -> None:
        self.config = config
        self._http = httpx.Client(
            base_url=config.base_url,
            headers={"Authorization": f"{config.auth_scheme} {config.token}"},
            verify=config.verify,
            timeout=config.timeout,
            transport=transport,
        )

    def __enter__(self) -> SplunkClient:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self._http.close()

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._request("GET", path, params=params)

    def post(
        self, path: str, data: dict[str, Any], *, timeout: float | None = None
    ) -> dict[str, Any]:
        """Non-mutating POST (e.g. a search job). Never gated by dry-run."""
        return self._request("POST", path, data=data, timeout=timeout)

    def write(self, method: str, path: str, data: dict[str, Any]) -> dict[str, Any]:
        """Mutating request. When dry_run is set, sends nothing and returns a preview."""
        if self.config.dry_run:
            return {
                "dry_run": True,
                "request": {"method": method, "path": "/" + path.lstrip("/"), "body": data},
                "target": self.config.base_url,
            }
        return self._request(method, path, data=data)

    def get_collection(
        self, path: str, params: dict[str, Any] | None = None, *, page: int = 200
    ) -> list[dict[str, Any]]:
        """Auto-paginate a Splunk collection endpoint and return every entry."""
        base = dict(params or {})
        offset: int = 0
        out: list[dict[str, Any]] = []
        while True:
            body = self._request("GET", path, params={**base, "count": page, "offset": offset})
            entries = body.get("entry") or []
            out.extend(entries)
            total = (body.get("paging") or {}).get("total")
            offset += len(entries)
            if not entries or len(entries) < page or (total is not None and offset >= total):
                return out

    def _request(self, method, path, *, params=None, data=None, timeout=None) -> dict[str, Any]:
        params = {**(params or {}), "output_mode": "json"}
        url = "/" + path.lstrip("/")
        for attempt in range(_MAX_RETRIES + 1):
            try:
                resp = self._http.request(
                    method,
                    url,
                    params=params,
                    data=data,
                    # Only None means "unset" — an explicit timeout (even 0) is honored.
                    timeout=self.config.timeout if timeout is None else timeout,
                )
            except httpx.HTTPError as exc:
                raise TransportError(
                    f"Could not reach Splunk at {self.config.base_url}: {exc}"
                ) from exc
            if resp.status_code in _RETRY_STATUS and attempt < _MAX_RETRIES:
                time.sleep(_retry_after(resp, attempt))
                continue
            return _handle(resp, method, url)
        raise TransportError("retries exhausted")  # pragma: no cover


def _retry_after(resp: httpx.Response, attempt: int) -> float:
    hdr = resp.headers.get("Retry-After")
    if hdr and hdr.isdigit():
        return float(hdr)
    return min(2.0**attempt, 8.0)


def _handle(resp: httpx.Response, method: str, url: str) -> dict[str, Any]:
    if resp.status_code == 401:
        raise AuthError("Authentication failed (401). Check SPLUNK_TOKEN.")
    if resp.status_code == 403:
        raise AuthError(f"Permission denied (403) for {method} {url}.")
    if resp.status_code == 404:
        raise NotFoundError(f"Not found: {url}")
    if resp.status_code >= 400:
        raise APIError(
            f"Splunk returned {resp.status_code} for {method} {url}", details=_safe_body(resp)
        )
    if not resp.content:
        return {}
    try:
        return resp.json()
    except ValueError:
        return {"raw": resp.text}


def _safe_body(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except ValueError:
        return resp.text[:500]
