"""Config-file profiles (stdlib ``configparser``). Click-free core.

A profile is a named bundle of connection settings so a user doesn't have to
export the same environment every session. The file is a plain INI; each
``[section]`` is one profile with any of these keys: ``url``, ``token``,
``session_key``, ``app``, ``owner``.

Resolution order for the file path is ``$VCT_SPLUNK_CONFIG``, else
``$XDG_CONFIG_HOME/vct-splunk/config``, else ``~/.config/vct-splunk/config``.

A profile only ever *fills gaps*: every consumer applies flag > env > profile >
default, so a profile never overrides an explicit flag or environment variable.
Reading is best-effort — a missing file is not an error.
"""

from __future__ import annotations

import configparser
import os
from pathlib import Path

from .errors import UsageError

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


def load_profile(name: str | None) -> dict[str, str]:
    """Return the named profile's keys, or ``{}`` when there is nothing to load.

    Args:
        name: The profile (INI section) name, or None to load nothing.

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
    except (OSError, configparser.Error):
        return {}
    if not parser.has_section(name):
        return {}
    section = parser[name]
    values = {key: section[key] for key in PROFILE_KEYS if key in section}
    if os.name == "posix" and any(values.get(key) for key in ("token", "session_key")):
        try:
            mode = path.stat().st_mode & 0o777
        except OSError:
            return {}
        if mode & 0o077:
            raise UsageError(f"Profile file {path} contains credentials and must have mode 0600.")
    return values
