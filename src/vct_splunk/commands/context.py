"""CLI context plus the shared ``command`` decorator. Shell layer (imports Click).

This module is the seam between Click (the user-facing shell) and the Click-free
core library. Two things live here:

* :class:`Ctx` — a small bundle of the options that every command shares (output
  format, the write-gating flags, and an optional base-URL override). Command
  bodies read this instead of reaching for globals.
* :func:`command` — a decorator that attaches those shared options to a *leaf*
  command, packs the parsed values into a :class:`Ctx`, and translates the
  core's typed :class:`SplunkError` exceptions into a clean stderr message plus
  the matching process exit code.

The shared options are attached to each leaf command (e.g. ``index list``) rather
than to the top-level group, so they work at the natural position on the command
line, for example ``splunk index list --output json``.
"""

from __future__ import annotations

import functools
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import click

from ..core.backends import deduce_backend
from ..core.client import SplunkClient, config_from_env
from ..core.errors import SplunkError
from ..core.profiles import load_profile
from . import output as out

if TYPE_CHECKING:
    from ..core.acs.client import AcsClient


class AliasedGroup(click.Group):
    """A Click group that also resolves extra verb aliases.

    Lets a group offer Splunk-CLI-style verbs (``add`` / ``edit`` / ``remove``)
    alongside our ``create`` / ``update`` / ``delete`` for familiarity, while
    keeping ``--help`` to the canonical names. Pass an ``aliases`` mapping of
    ``{alias: real_name}`` to the group decorator.
    """

    def __init__(self, *args: Any, aliases: dict[str, str] | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._aliases = aliases or {}

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        return super().get_command(ctx, self._aliases.get(cmd_name, cmd_name))


@dataclass
class Ctx:
    """The options shared by every ``splunk`` subcommand, resolved once per call.

    Attributes:
        output_mode: Either ``"json"`` or ``"table"`` — already resolved from the
            ``--output``/``--table`` flags and whether stdout is a TTY.
        dry_run: When True, mutating commands preview the request instead of
            sending it.
        yes: When True, skip the interactive confirmation prompt before a write
            (required when running non-interactively, e.g. from a script).
        base_url: An explicit Splunk management URL from ``--base-url`` that
            overrides the ``SPLUNK_URL`` environment variable, or None.
        app: The Splunk app namespace from ``--app`` / ``$SPLUNK_APP``, or None.
            Used by namespaced resources (e.g. saved searches); ignored by
            system-level ones (e.g. indexes).
        owner: The owner namespace from ``--owner`` / ``$SPLUNK_OWNER``, or None.
        profile: The active config-file profile name from ``--profile`` /
            ``$SPLUNK_PROFILE``, or None. Supplies connection settings only where
            a flag and env var leave them unset (flag > env > profile > default).
        backend: The backend deduced from the target URL (``"enterprise"`` or
            ``"cloud"``) -- never user-set. Commands that both backends serve use
            it to route to splunkd REST or ACS; writes use it to stop on Cloud.
    """

    output_mode: str
    dry_run: bool
    yes: bool
    base_url: str | None
    app: str | None = None
    owner: str | None = None
    profile: str | None = None
    backend: str = "enterprise"

    def client(self) -> SplunkClient:
        """Build a :class:`SplunkClient` from the environment plus this context.

        Credentials and TLS settings are read from flags, the environment, and
        the active profile (see :func:`vct_splunk.core.client.config_from_env`);
        the ``dry_run`` flag is carried over from the command line so that writes
        can be previewed.

        Returns:
            A ready-to-use client. Use it as a context manager so its underlying
            HTTP connection is closed afterwards::

                with ctx.client() as c:
                    ...
        """
        cfg = config_from_env(self.base_url, profile=self.profile)
        cfg.dry_run = self.dry_run
        return SplunkClient(cfg)

    def acs_client(self) -> AcsClient:
        """Build an :class:`AcsClient` for the deduced Cloud stack.

        Separate config from the REST :meth:`client`: the stack is derived from
        the cloud host (``$SPLUNK_URL`` or ``--base-url``), and the ACS Bearer
        token is read from ``$SPLUNK_ACS_TOKEN``. Use as a context manager.
        """
        from ..core.acs.client import AcsClient, acs_config_from_env
        from ..core.backends import cloud_stack_from_url

        stack = cloud_stack_from_url(self.base_url)
        return AcsClient(acs_config_from_env(stack))

    def meta(self) -> dict[str, str | None]:
        """Return the metadata block that is attached to every JSON response.

        Right now this is just the target Splunk URL, so a piece of output can be
        traced back to the instance it came from.
        """
        return {"target": self.base_url}


def command(fn: Callable) -> Callable:
    """Attach the shared options to a leaf command and handle core errors.

    Use this on a function whose first parameter is a :class:`Ctx`. The returned
    wrapper gains the common Click options (``--output``/``--table``/
    ``--dry-run``/``--yes``/``--base-url``/``--app``/``--owner``), so the
    command body can focus on its own arguments. Any :class:`SplunkError` raised
    by the core is caught and rendered to stderr with the correct exit code via
    :func:`vct_splunk.commands.output.fail`.

    Args:
        fn: The leaf command implementation, called as ``fn(ctx, **command_args)``.

    Returns:
        A Click-decorated callable suitable for registering on a command group.
    """

    @functools.wraps(fn)
    def wrapper(output, table, dry_run, yes, base_url, app, owner, profile, **kwargs: Any) -> Any:
        # Click passes every option to the callback by name. The shared options
        # are named explicitly here; the command's own arguments arrive untouched
        # in **kwargs and are forwarded straight through to fn.
        try:
            profile = profile or os.environ.get("SPLUNK_PROFILE")
            prof = load_profile(profile, credentials=False)
            target = base_url or os.environ.get("SPLUNK_URL") or prof.get("url")
            ctx = Ctx(
                out.resolve_mode(output, table),
                dry_run,
                yes,
                target,
                app=app or os.environ.get("SPLUNK_APP") or prof.get("app"),
                owner=owner or os.environ.get("SPLUNK_OWNER") or prof.get("owner"),
                profile=profile,
                backend=deduce_backend(target),
            )
            return fn(ctx, **kwargs)
        except SplunkError as exc:
            # The core stays Click-free and raises typed errors; the shell layer
            # turns them into a JSON error envelope on stderr plus an exit code.
            out.fail(exc)

    # Click applies decorators bottom-up, so --help lists these in reverse order.
    options = [
        click.option(
            "--profile",
            default=None,
            help="Config-file profile name (overridden by flags/env; or $SPLUNK_PROFILE).",
        ),
        click.option(
            "--owner",
            default=None,
            help="Owner namespace (default: '-' wildcard for reads, 'nobody' for writes).",
        ),
        click.option(
            "--app",
            default=None,
            help="App namespace. Writes require it and never default to 'search'.",
        ),
        click.option(
            "--base-url", default=None, help="Splunk management URL (overrides $SPLUNK_URL)."
        ),
        click.option(
            "-y",
            "--yes",
            is_flag=True,
            help="Skip confirmation (required for writes when non-interactive).",
        ),
        click.option("--dry-run", is_flag=True, help="Preview writes without sending them."),
        click.option("--table", is_flag=True, help="Shortcut for --output table."),
        click.option(
            "--output",
            type=click.Choice(["json", "table"]),
            default=None,
            help="Output format (default: table on a TTY, JSON when piped).",
        ),
    ]
    for option in options:
        wrapper = option(wrapper)
    return wrapper
