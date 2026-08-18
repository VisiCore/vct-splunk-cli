"""Typed configuration objects. Click-free.

:class:`SplunkConfig` is the single bundle of connection and credential
settings that the API client (:mod:`vct_splunk.api.client`) and the auth layer
(:mod:`vct_splunk.auth.session`) consume. It carries credential *sources*
(token, session key, or username/password) rather than a resolved header —
resolution happens lazily, per request, in the auth transport, so a
long-running consumer (a web backend embedding this package) can re-login
transparently when a session expires.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SplunkConfig:
    """Connection and credential settings for one Splunk target.

    Attributes:
        base_url: The management URL, e.g. ``https://host:8089``.
        token: A Splunk JWT, sent as ``Authorization: Bearer <token>``.
        session_key: A session key from ``/services/auth/login``, sent as
            ``Authorization: Splunk <key>``. Used when no token is set.
        username: Login fallback when neither token nor session key is set.
        password: Login fallback partner of ``username``.
        verify: TLS verification — True/False, or a path to a CA bundle.
        timeout: Default per-request timeout in seconds.
        dry_run: When True, mutating requests are previewed and never sent.
    """

    base_url: str
    token: str | None = None
    session_key: str | None = None
    username: str | None = None
    password: str | None = None
    verify: bool | str = True
    timeout: float = 30.0
    dry_run: bool = False


@dataclass(frozen=True)
class AuthStatus:
    """Resolved target and authentication scheme without performing login."""

    base_url: str
    auth_scheme: str
