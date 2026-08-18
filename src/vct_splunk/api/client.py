"""HTTP client with auth interceptor and retry logic. Click-free.

Mirrors the cribl-cli ``api/client`` design: a layered httpx transport stack
owns the cross-cutting transport concerns, so every request behaves the same
no matter which endpoint module sends it::

    Request
      -> AuthTransport       (injects the Authorization header, per request)
        -> RetryTransport    (retries 429/503 honoring Retry-After)
          -> httpx.HTTPTransport (sends the request)

Auth is resolved *per request* by :class:`AuthTransport` via
:func:`vct_splunk.auth.session.get_auth_header` — a static token passes
straight through, while a username/password login is minted lazily and cached,
so an embedding process (a web backend) survives session expiry without
restarting. The credential only ever lives in a header and is never logged.

:class:`SplunkClient` is the thin envelope-aware wrapper the endpoint modules
(:mod:`vct_splunk.api.endpoints`) take as their first argument: it owns
Splunk's ``output_mode=json`` parameter, the ``entry[].content`` decoding
hand-off, pagination, typed error mapping, and the dry-run gate for mutating
requests (previews are returned as data and nothing is sent).

Module-level ``get_client`` / ``set_client`` allow an embedding application to
initialize one client up front, cribl-style; the CLI itself builds a client per
command instead.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from ..auth.session import clear_session_cache, get_auth_header, is_mintable
from ..config.types import SplunkConfig
from ..utils.errors import APIError, AuthError, NotFoundError, TransportError
from ..utils.redact import safe_target

_RETRY_STATUS = {429, 503}
_MAX_RETRIES = 3

_client: SplunkClient | None = None
_config_error: str | None = None


class AuthTransport(httpx.BaseTransport):
    """Transport wrapper that injects the Authorization header into every request.

    Resolution happens here — per request, not at client construction — so a
    lazily minted session key can be refreshed transparently when it expires.

    When the credential is a username/password (a session key we can re-mint), a
    401 is treated as a possibly-stale session rather than a hard failure: Splunk
    invalidates session keys server-side on events like a restart. In that case
    the cache is dropped, a fresh login is performed, and the request is retried
    once. A static token or session key is not refreshable, so its 401 passes
    straight through as a genuine auth error.
    """

    def __init__(self, transport: httpx.BaseTransport, config: SplunkConfig) -> None:
        self._transport = transport
        self._config = config

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        request.headers["Authorization"] = get_auth_header(self._config)
        response = self._transport.handle_request(request)
        if response.status_code == 401 and is_mintable(self._config):
            response.close()
            clear_session_cache()
            request.headers["Authorization"] = get_auth_header(self._config)
            response = self._transport.handle_request(request)
        return response


class RetryTransport(httpx.BaseTransport):
    """Transport that retries requests on 429/503, honoring ``Retry-After``."""

    def __init__(self, transport: httpx.BaseTransport) -> None:
        self._transport = transport

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        response = self._transport.handle_request(request)
        for attempt in range(_MAX_RETRIES):
            if response.status_code not in _RETRY_STATUS:
                return response
            response.close()
            time.sleep(_retry_after(response, attempt))
            response = self._transport.handle_request(request)
        return response


def _retry_after(resp: httpx.Response, attempt: int) -> float:
    hdr = resp.headers.get("Retry-After")
    if hdr and hdr.isdigit():
        return float(hdr)
    return min(2.0**attempt, 8.0)


class SplunkClient:
    """Envelope-aware Splunk REST client over the layered transport stack.

    Args:
        config: The resolved connection/credential settings.
        transport: Optional innermost transport, for tests
            (``httpx.MockTransport``). The auth and retry layers still wrap it,
            so tests exercise the real stack.
    """

    def __init__(
        self, config: SplunkConfig, *, transport: httpx.BaseTransport | None = None
    ) -> None:
        self.config = config
        # TLS settings live on the innermost transport: httpx ignores `verify`
        # when a custom transport chain is supplied to the Client.
        inner = transport if transport is not None else httpx.HTTPTransport(verify=config.verify)
        stack: httpx.BaseTransport = AuthTransport(RetryTransport(inner), config)
        self._http = httpx.Client(
            base_url=config.base_url,
            timeout=config.timeout,
            transport=stack,
        )

    def __enter__(self) -> SplunkClient:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self._http.close()

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """GET an endpoint and return its parsed JSON response."""
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
                "target": safe_target(self.config.base_url),
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
                "target": safe_target(self.config.base_url),
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
                f"Could not reach Splunk at {safe_target(self.config.base_url)}: {exc}"
            ) from exc
        return _handle(resp, method, url)


def create_client(
    config: SplunkConfig, *, transport: httpx.BaseTransport | None = None
) -> SplunkClient:
    """Create a :class:`SplunkClient` over the auth/retry transport stack."""
    return SplunkClient(config, transport=transport)


def get_client() -> SplunkClient:
    """Return the process-wide client set via :func:`set_client`.

    This is the cribl-style embedding hook: an application (e.g. a web backend)
    initializes one client at startup and endpoint calls share it. The CLI does
    not use it — each command builds and closes its own client.
    """
    if _client is None:
        if _config_error:
            raise TransportError(_config_error)
        raise TransportError("API client not initialized")
    return _client


def set_client(client: SplunkClient | None) -> None:
    """Install (or clear) the process-wide client returned by :func:`get_client`."""
    global _client
    _client = client


def set_config_error(msg: str) -> None:
    """Record why client initialization failed, surfaced by :func:`get_client`."""
    global _config_error
    _config_error = msg


def _handle(resp: httpx.Response, method: str, url: str) -> Any:
    if resp.status_code == 401:
        raise AuthError("Authentication failed (401). Check SPLUNK_TOKEN or SPLUNK_SESSION_KEY.")
    if resp.status_code == 403:
        raise AuthError(f"Permission denied (403) for {method} {url}.")
    if resp.status_code == 404:
        raise NotFoundError(f"Not found: {url}")
    if resp.status_code >= 400:
        raise APIError(
            f"Splunk returned {resp.status_code} for {method} {url}",
            status=resp.status_code,
            details=_safe_body(resp),
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
