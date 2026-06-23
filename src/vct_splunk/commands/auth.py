"""`splunk auth` commands: session login and auth status. Shell layer (imports Click).

``auth login`` exchanges a username/password for a Splunk session key and prints
it (a secret hint goes to stderr; nothing is written to disk). ``auth status``
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


def _resolve_url(base_url: str | None, profile: str | None) -> str:
    """Resolve the management URL by flag > env > profile (no credential needed)."""
    url = base_url or os.environ.get("SPLUNK_URL") or load_profile(profile).get("url")
    if not url:
        raise UsageError("No Splunk URL. Set SPLUNK_URL or pass --base-url.")
    return url.rstrip("/")


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
    url = _resolve_url(ctx.base_url, ctx.profile)
    key = core.login(url, _resolve_username(username), _resolve_password(), verify=_verify())
    # The key itself is data on stdout; the usage hint is a diagnostic on stderr.
    click.echo(f"export SPLUNK_SESSION_KEY={key}", err=True)
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
