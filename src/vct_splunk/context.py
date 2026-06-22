"""CLI context + the shared `command` decorator. Shell layer (imports Click).

`command` attaches the common flags (output/table/dry-run/yes/base-url/verbose) to a
leaf command so they work at the natural position (e.g. `splunk index list --output json`),
builds a Ctx, and converts core SplunkErrors into a clean stderr envelope + exit code.
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
    output_mode: str
    dry_run: bool
    yes: bool
    verbose: bool
    base_url: str | None

    def client(self) -> SplunkClient:
        cfg = config_from_env(self.base_url)
        cfg.dry_run = self.dry_run
        return SplunkClient(cfg)

    def meta(self) -> dict[str, str | None]:
        return {"target": self.base_url or os.environ.get("SPLUNK_URL")}


def command(fn: Callable) -> Callable:
    @functools.wraps(fn)
    def wrapper(output, table, dry_run, yes, base_url, verbose, **kwargs: Any) -> Any:
        ctx = Ctx(out.resolve_mode(output, table), dry_run, yes, verbose, base_url)
        try:
            return fn(ctx, **kwargs)
        except SplunkError as exc:
            out.fail(exc)

    options = [
        click.option("--verbose", is_flag=True, help="Verbose diagnostics on stderr."),
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
