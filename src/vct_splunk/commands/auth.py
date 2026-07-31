"""`splunk auth` commands: session login and auth status. Shell layer (imports Click).

``auth login`` exchanges a username/password for a Splunk session key and prints
it as command data. ``auth status``
reports the resolved target and which auth scheme is active, without revealing
any secret value.
"""

from __future__ import annotations

import os
import sys

import click

from ..core import auth as core
from ..core.errors import UsageError
from ..core.profiles import load_profile
from . import output as out
from .context import command


def _verify() -> bool | str:
    """TLS verification from the environment, matching the main client."""
    ca = os.environ.get("SPLUNK_CA_BUNDLE")
    on = os.environ.get("SPLUNK_VERIFY", "true").strip().lower() not in {"0", "false", "no"}
    return ca or on


def _resolve_username(username: str | None) -> str:
    """Return the username from the flag, ``$SPLUNK_USERNAME``, or a TTY prompt."""
    username = username or os.environ.get("SPLUNK_USERNAME")
    if username:
        return username
    if not sys.stdin.isatty():
        raise UsageError("No username. Set SPLUNK_USERNAME or pass --username.")
    return click.prompt("Username", err=True)


def _resolve_password() -> str:
    """Return the password from ``$SPLUNK_PASSWORD`` or a no-echo TTY prompt.

    Never a flag — a secret on the command line would leak into shell history and
    process listings.
    """
    password = os.environ.get("SPLUNK_PASSWORD")
    if password:
        return password
    if not sys.stdin.isatty():
        raise UsageError("No password. Set SPLUNK_PASSWORD (run interactively to be prompted).")
    return click.prompt("Password", hide_input=True, err=True)


@click.group()
def auth() -> None:
    """Authenticate to Splunk and inspect the active auth scheme."""


@auth.command("login")
@click.option("--username", default=None, help="Splunk username (or $SPLUNK_USERNAME; prompts).")
@command
def login(ctx, username: str | None) -> None:
    """Exchange a username/password for a session key (printed to stdout).

    The password is read from ``$SPLUNK_PASSWORD`` or a no-echo prompt — never a
    flag. The session key is printed as data; export it as ``SPLUNK_SESSION_KEY``
    to use it (this command does not persist it).
    """
    url = ctx.base_url
    if not url:
        raise UsageError("No Splunk URL. Set SPLUNK_URL, select a profile, or pass --base-url.")
    key = core.login(url, _resolve_username(username), _resolve_password(), verify=_verify())
    out.emit({"session_key": key}, ctx.output_mode, ctx.meta())


@auth.command("status")
@command
def status(ctx) -> None:
    """Report the resolved target URL and active auth scheme (no secret shown)."""
    prof = load_profile(ctx.profile)
    url = ctx.base_url or os.environ.get("SPLUNK_URL") or prof.get("url")
    if os.environ.get("SPLUNK_TOKEN") or prof.get("token"):
        scheme = "Bearer"
    elif os.environ.get("SPLUNK_SESSION_KEY") or prof.get("session_key"):
        scheme = "Splunk"
    else:
        scheme = "none"
    out.emit({"target": url, "auth_scheme": scheme}, ctx.output_mode, ctx.meta())
