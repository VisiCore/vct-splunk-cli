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
from .profiles import load_profile

_RETRY_STATUS = {429, 503}
_MAX_RETRIES = 3


@dataclass
class ClientConfig:
    base_url: str
    token: str
    verify: bool | str = True  # True/False, or a path to a CA bundle
    timeout: float = 30.0
    dry_run: bool = False
    # Splunk accepts two REST auth schemes via the Authorization header: a JWT as
    # "Bearer <token>" (the default) and a session key as "Splunk <sessionKey>".
    auth_scheme: str = "Bearer"


def config_from_env(base_url: str | None = None, *, profile: str | None = None) -> ClientConfig:
    """Build a :class:`ClientConfig` from flags, the environment, and a profile.

    Precedence for each value is **flag > env > profile > built-in default**: an
    explicit ``base_url`` (from ``--base-url``) wins, then the environment, then
    the active config-file profile (see :func:`vct_splunk.core.profiles.load_profile`),
    then any hard-coded fallback. The profile is consulted only when the flag and
    env var are both unset, so callers that set ``SPLUNK_URL`` / ``SPLUNK_TOKEN``
    keep their existing behavior.

    Args:
        base_url: An explicit management URL from ``--base-url``, or None.
        profile: The active profile name (from ``--profile`` / ``$SPLUNK_PROFILE``),
            or None for no profile.

    Returns:
        A resolved config. Auth is ``Bearer`` when a token is present, else
        ``Splunk`` when a session key is present.

    Raises:
        UsageError: If no URL or no credential can be resolved.
    """
    prof = load_profile(profile)
    url = base_url or os.environ.get("SPLUNK_URL") or prof.get("url")
    if not url:
        raise UsageError("No Splunk URL. Set SPLUNK_URL or pass --base-url.")
    token = os.environ.get("SPLUNK_TOKEN") or prof.get("token")
    session_key = os.environ.get("SPLUNK_SESSION_KEY") or prof.get("session_key")
    if token:
        scheme, credential = "Bearer", token
    elif session_key:
        scheme, credential = "Splunk", session_key
    else:
        raise UsageError("No auth credential. Set SPLUNK_TOKEN or SPLUNK_SESSION_KEY.")
    ca = os.environ.get("SPLUNK_CA_BUNDLE")
    verify_env = os.environ.get("SPLUNK_VERIFY", "true").strip().lower() not in {"0", "false", "no"}
    return ClientConfig(
        base_url=url.rstrip("/"), token=credential, verify=ca or verify_env, auth_scheme=scheme
    )


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

    def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """GET a JSON document endpoint (e.g. KV Store data) and return it as-is.

        Unlike :meth:`get`, the response is plain JSON (an array for a collection,
        an object for one record) rather than the ``entry[].content`` envelope, so
        the return type is the raw parsed value.
        """
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

    def write_json(self, method: str, path: str, body: Any) -> Any:
        """Mutating request with a JSON body (Content-Type: application/json).

        The KV Store *data* endpoints are a JSON document store, not the Splunk
        ``entry[].content`` envelope: requests carry a JSON body and responses are
        plain JSON objects/arrays. This is the JSON-body sibling of :meth:`write`;
        it is dry-run gated the same way and returns the parsed JSON otherwise.
        """
        if self.config.dry_run:
            return {
                "dry_run": True,
                "request": {"method": method, "path": "/" + path.lstrip("/"), "body": body},
                "target": self.config.base_url,
            }
        return self._request(method, path, json_body=body)

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

    def _request(
        self, method, path, *, params=None, data=None, json_body=None, timeout=None
    ) -> Any:
        # The classic Splunk endpoints speak the entry/content envelope and need
        # output_mode=json; the KV Store data store is already JSON, so a JSON-body
        # request skips that param and sends application/json instead of form data.
        params = dict(params or {})
        if json_body is None:
            params["output_mode"] = "json"
        url = "/" + path.lstrip("/")
        for attempt in range(_MAX_RETRIES + 1):
            try:
                resp = self._http.request(
                    method,
                    url,
                    params=params,
                    data=data,
                    json=json_body,
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


def _handle(resp: httpx.Response, method: str, url: str) -> Any:
    if resp.status_code == 401:
        raise AuthError("Authentication failed (401). Check SPLUNK_TOKEN or SPLUNK_SESSION_KEY.")
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
