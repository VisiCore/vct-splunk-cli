"""Credential resolution and session login. Click-free.

Mirrors the cribl-cli ``auth/oauth`` role for Splunk's two REST auth schemes:

* A JWT (``SPLUNK_TOKEN``) is sent as ``Authorization: Bearer <token>``.
* A session key (``SPLUNK_SESSION_KEY``, or one minted here from a
  username/password login) is sent as ``Authorization: Splunk <key>``.

:func:`get_auth_header` is called **per request** by the client's
:class:`~vct_splunk.api.client.AuthTransport`, so a long-running consumer (a
web backend embedding this package) re-logs-in transparently when a cached
session key expires. Static credentials pass straight through; only the
username/password path caches, with an expiry margin like the cribl CLI's
token cache.

:func:`login` is the one REST call that does **not** carry an Authorization
header: the credentials travel in the form body, and Splunk hands back a
session key.
"""

from __future__ import annotations

import time

import httpx

from ..config.types import SplunkConfig
from ..utils.errors import APIError, AuthError, TransportError
from ..utils.redact import safe_target

#: How long a minted session key is reused before re-login. Splunk's default
#: session timeout is 60 minutes; refreshing five minutes early keeps a
#: long-lived process from ever sending a just-expired key.
SESSION_TTL_SECONDS = 55 * 60

_cached_session: dict | None = (
    None  # {"key": (base_url, username), "header": str, "expires_at": float}
)


def clear_session_cache() -> None:
    """Drop any cached login session (used by tests and re-auth flows)."""
    global _cached_session
    _cached_session = None


def is_mintable(config: SplunkConfig) -> bool:
    """True when the credential is a username/password we can re-mint on demand.

    A static token or session key cannot be refreshed — a 401 from one is a real
    authentication failure. A username/password, by contrast, mints a session key
    that Splunk can invalidate server-side (notably on a restart), so a 401 there
    is recoverable by logging in again. The client uses this to decide whether to
    drop the cache and retry once after a 401.
    """
    return not config.token and not config.session_key and bool(config.username and config.password)


def get_auth_header(config: SplunkConfig) -> str:
    """Return the ``Authorization`` header value for *config*.

    A token or session key is used as-is. With only a username/password, a
    session key is minted via :func:`login` and cached until
    :data:`SESSION_TTL_SECONDS` elapses.

    Raises:
        AuthError: If *config* carries no credential source.
    """
    global _cached_session
    if config.token:
        return f"Bearer {config.token}"
    if config.session_key:
        return f"Splunk {config.session_key}"
    if config.username and config.password:
        cache_key = (config.base_url, config.username)
        if (
            _cached_session
            and _cached_session["key"] == cache_key
            and time.time() < _cached_session["expires_at"]
        ):
            return _cached_session["header"]
        key = login(
            config.base_url,
            config.username,
            config.password,
            verify=config.verify,
            timeout=config.timeout,
        )
        header = f"Splunk {key}"
        _cached_session = {
            "key": cache_key,
            "header": header,
            "expires_at": time.time() + SESSION_TTL_SECONDS,
        }
        return header
    raise AuthError(
        "No auth. Set SPLUNK_TOKEN (a JWT) or SPLUNK_SESSION_KEY "
        "(a session key from /services/auth/login)."
    )


def login(
    url: str,
    username: str,
    password: str,
    *,
    verify: bool | str = True,
    timeout: float = 30.0,
    transport: httpx.BaseTransport | None = None,
) -> str:
    """Exchange a username/password for a Splunk session key.

    POSTs ``username`` / ``password`` (form-encoded, ``output_mode=json``) to
    ``{url}/services/auth/login`` with no Authorization header, and returns the
    ``sessionKey`` from the JSON response (``{"sessionKey": "..."}``).

    Args:
        url: The Splunk management base URL (e.g. ``https://host:8089``).
        username: The Splunk account name.
        password: The account password (read from env/prompt, never a flag).
        verify: TLS verification — True/False or a CA-bundle path.
        timeout: Request timeout in seconds.
        transport: An optional httpx transport, for tests (``MockTransport``).

    Returns:
        The session key string.

    Raises:
        AuthError: On a 401/403 (bad credentials) or a missing ``sessionKey``.
        APIError: On any other non-2xx response.
        TransportError: If Splunk cannot be reached.
    """
    endpoint = f"{url.rstrip('/')}/services/auth/login"
    try:
        with httpx.Client(verify=verify, timeout=timeout, transport=transport) as http:
            resp = http.post(
                endpoint,
                data={"username": username, "password": password, "output_mode": "json"},
            )
    except httpx.HTTPError as exc:
        raise TransportError(f"Could not reach Splunk at {safe_target(url)}: {exc}") from exc
    if resp.status_code in {401, 403}:
        raise AuthError(f"Login failed ({resp.status_code}). Check the username and password.")
    if resp.status_code >= 400:
        raise APIError(f"Splunk returned {resp.status_code} for POST /services/auth/login")
    try:
        key = resp.json().get("sessionKey")
    except ValueError:
        key = None
    if not key:
        raise AuthError("Login response did not include a sessionKey.")
    return key
