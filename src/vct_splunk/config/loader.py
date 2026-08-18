"""Config loading: INI profiles plus env-var and flag merging. Click-free.

Mirrors the cribl-cli ``config/loader`` role: one module owns "where do
connection settings come from". A profile is a named ``[section]`` in a plain
INI file with any of these keys: ``url``, ``token``, ``session_key``, ``app``,
``owner``. Resolution order for the file path is ``$VCT_SPLUNK_CONFIG``, else
``$XDG_CONFIG_HOME/vct-splunk/config``, else ``~/.config/vct-splunk/config``.

Every value applies **flag > env > profile > built-in default**: a profile only
ever fills gaps, never overriding an explicit flag or environment variable.
Reading is best-effort — a missing file is not an error.

:func:`load_config` merges those sources into a
:class:`~vct_splunk.config.types.SplunkConfig`. It validates that *some*
credential source exists but performs no network I/O — the actual login (when
only a username/password is available) happens lazily in
:mod:`vct_splunk.auth.session`, per request, via the client's auth transport.
"""

from __future__ import annotations

import configparser
import os
from pathlib import Path

from ..utils.errors import UsageError
from .types import AuthStatus, SplunkConfig

#: The profile keys a section may define. Anything else is ignored.
PROFILE_KEYS = ("url", "token", "session_key", "app", "owner")


def config_path() -> Path:
    """Return the config-file path, honoring ``$VCT_SPLUNK_CONFIG`` / XDG.

    The file need not exist; this only computes where it *would* live.
    """
    override = os.environ.get("VCT_SPLUNK_CONFIG")
    if override:
        return Path(override)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "vct-splunk" / "config"


def load_profile(name: str | None, *, credentials: bool = True) -> dict[str, str]:
    """Return the named profile's keys, or ``{}`` when there is nothing to load.

    Args:
        name: The profile (INI section) name, or None to load nothing.
        credentials: When False, the secret-bearing keys (``token``,
            ``session_key``) are excluded, so a caller that only needs the URL
            or namespace cannot accidentally pull a credential.

    Returns:
        A dict of the profile's recognized keys (see :data:`PROFILE_KEYS`).
        Empty when ``name`` is None, the file is absent or unreadable, or the
        section does not exist — a missing file is deliberately not an error.
    """
    if not name:
        return {}
    path = config_path()
    if not path.is_file():
        return {}
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read(path)
    except UnicodeError as exc:
        raise UsageError(f"Profile file {path} is not valid UTF-8.") from exc
    except configparser.Error as exc:
        raise UsageError(f"Profile file {path} is malformed: {exc}.") from exc
    except OSError:
        return {}
    if not parser.has_section(name):
        return {}
    section = parser[name]
    keys = (
        PROFILE_KEYS
        if credentials
        else tuple(key for key in PROFILE_KEYS if key not in {"token", "session_key"})
    )
    values = {key: section[key] for key in keys if key in section}
    return values


def require_private_profile() -> None:
    """Require owner-only access before a selected profile credential is used."""
    if os.name != "posix":
        return
    path = config_path()
    try:
        mode = path.stat().st_mode & 0o777
    except OSError:
        return
    if mode & 0o077:
        raise UsageError(
            f"Profile file {path} contains selected credentials and must have mode 0600."
        )


def load_config(base_url: str | None = None, *, profile: str | None = None) -> SplunkConfig:
    """Build a :class:`SplunkConfig` from flags, the environment, and a profile.

    Precedence for each value is **flag > env > profile > built-in default**: an
    explicit ``base_url`` (from ``--base-url``) wins, then the environment, then
    the active config-file profile, then any hard-coded fallback. The profile is
    consulted only when the flag and env var are both unset, so callers that set
    ``SPLUNK_URL`` / ``SPLUNK_TOKEN`` keep their existing behavior.

    Credential sources, in priority order: ``SPLUNK_TOKEN`` (a JWT, sent as
    ``Bearer``), ``SPLUNK_SESSION_KEY`` (sent as ``Splunk``), then
    ``SPLUNK_USERNAME``/``SPLUNK_PASSWORD`` (exchanged for a session key lazily,
    on the first request). No network I/O happens here.

    Args:
        base_url: An explicit management URL from ``--base-url``, or None.
        profile: The active profile name (from ``--profile`` / ``$SPLUNK_PROFILE``),
            or None for no profile.

    Returns:
        A resolved config carrying whichever credential sources were found.

    Raises:
        UsageError: If no URL or no credential source can be resolved.
    """
    status, prof, verify = _resolve_target(base_url, profile)
    env_token = os.environ.get("SPLUNK_TOKEN")
    env_session_key = os.environ.get("SPLUNK_SESSION_KEY")
    token = env_token or prof.get("token")
    session_key = env_session_key or prof.get("session_key")
    username = os.environ.get("SPLUNK_USERNAME")
    password = os.environ.get("SPLUNK_PASSWORD")
    if token:
        if not env_token:
            require_private_profile()
        session_key = username = password = None
    elif session_key:
        if not env_session_key:
            require_private_profile()
        username = password = None
    elif not (username and password):
        raise UsageError(
            "No auth. Set SPLUNK_TOKEN (a JWT) or SPLUNK_SESSION_KEY "
            "(a session key from /services/auth/login)."
        )
    return SplunkConfig(
        base_url=status.base_url,
        token=token,
        session_key=session_key,
        username=username,
        password=password,
        verify=verify,
    )


def auth_status(base_url: str | None = None, *, profile: str | None = None) -> AuthStatus:
    """Resolve the active auth scheme without exchanging username/password."""
    status, prof, _verify = _resolve_target(base_url, profile)
    env_token = os.environ.get("SPLUNK_TOKEN")
    env_session_key = os.environ.get("SPLUNK_SESSION_KEY")
    if env_token or prof.get("token"):
        if not env_token:
            require_private_profile()
        scheme = "Bearer"
    elif env_session_key or prof.get("session_key"):
        if not env_session_key:
            require_private_profile()
        scheme = "Splunk"
    elif os.environ.get("SPLUNK_USERNAME") and os.environ.get("SPLUNK_PASSWORD"):
        scheme = "Splunk"
    else:
        scheme = "none"
    return AuthStatus(status.base_url, scheme)


def _resolve_target(
    base_url: str | None, profile: str | None
) -> tuple[AuthStatus, dict[str, str], bool | str]:
    """Resolve shared URL, profile, and TLS inputs without authenticating."""
    prof = load_profile(profile)
    url = base_url or os.environ.get("SPLUNK_URL") or prof.get("url")
    if not url:
        raise UsageError("No Splunk URL. Set SPLUNK_URL or pass --base-url.")
    ca = os.environ.get("SPLUNK_CA_BUNDLE")
    verify = ca or (
        os.environ.get("SPLUNK_VERIFY", "true").strip().lower() not in {"0", "false", "no"}
    )
    return AuthStatus(url.rstrip("/"), "none"), prof, verify
