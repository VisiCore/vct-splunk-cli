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
from dataclasses import dataclass
from typing import Any, Callable

import click

from . import output as out
from .client import SplunkClient, config_from_env
from .errors import SplunkError


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
    """

    output_mode: str
    dry_run: bool
    yes: bool
    base_url: str | None

    def client(self) -> SplunkClient:
        """Build a :class:`SplunkClient` from the environment plus this context.

        Credentials and TLS settings are read from the environment (see
        :func:`vct_splunk.client.config_from_env`); the ``dry_run`` flag is
        carried over from the command line so that writes can be previewed.

        Returns:
            A ready-to-use client. Use it as a context manager so its underlying
            HTTP connection is closed afterwards::

                with ctx.client() as c:
                    ...
        """
        cfg = config_from_env(self.base_url)
        cfg.dry_run = self.dry_run
        return SplunkClient(cfg)

    def meta(self) -> dict[str, str | None]:
        """Return the metadata block that is attached to every JSON response.

        Right now this is just the target Splunk URL, so a piece of output can be
        traced back to the instance it came from.
        """
        return {"target": self.base_url or os.environ.get("SPLUNK_URL")}


def command(fn: Callable) -> Callable:
    """Attach the shared options to a leaf command and handle core errors.

    Use this on a function whose first parameter is a :class:`Ctx`. The returned
    wrapper gains the common Click options (``--output``/``--table``/
    ``--dry-run``/``--yes``/``--base-url``), so the command body can focus on its
    own arguments. Any :class:`SplunkError` raised by the core is caught and
    rendered to stderr with the correct exit code via
    :func:`vct_splunk.output.fail`.

    Args:
        fn: The leaf command implementation, called as ``fn(ctx, **command_args)``.

    Returns:
        A Click-decorated callable suitable for registering on a command group.
    """

    @functools.wraps(fn)
    def wrapper(output, table, dry_run, yes, base_url, **kwargs: Any) -> Any:
        # Click passes every option to the callback by name. The shared options
        # are named explicitly here; the command's own arguments arrive untouched
        # in **kwargs and are forwarded straight through to fn.
        ctx = Ctx(out.resolve_mode(output, table), dry_run, yes, base_url)
        try:
            return fn(ctx, **kwargs)
        except SplunkError as exc:
            # The core stays Click-free and raises typed errors; the shell layer
            # turns them into a JSON error envelope on stderr plus an exit code.
            out.fail(exc)

    # Click applies decorators bottom-up, so this list ends up reading in reverse
    # order in --help. The order is purely cosmetic.
    options = [
        click.option("--base-url", default=None, help="Splunk management URL (overrides $SPLUNK_URL)."),
        click.option("-y", "--yes", is_flag=True, help="Skip confirmation (required for writes when non-interactive)."),
        click.option("--dry-run", is_flag=True, help="Preview writes without sending them."),
        click.option("--table", is_flag=True, help="Shortcut for --output table."),
        click.option(
            "--output", type=click.Choice(["json", "table"]), default=None,
            help="Output format (default: table on a TTY, JSON when piped).",
        ),
    ]
    for option in options:
        wrapper = option(wrapper)
    return wrapper
