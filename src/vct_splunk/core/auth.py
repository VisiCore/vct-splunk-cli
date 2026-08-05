"""Session login against ``/services/auth/login``. Click-free core.

This is the one REST call that does **not** carry an Authorization header: the
credentials travel in the form body, and Splunk hands back a session key the
caller then uses as ``Authorization: Splunk <sessionKey>``. We keep it apart
from :class:`~vct_splunk.core.client.SplunkClient` (which always attaches a token
header) for exactly that reason.
"""

from __future__ import annotations

import httpx

from .errors import APIError, AuthError, TransportError
from .redact import safe_target


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
