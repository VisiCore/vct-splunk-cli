"""`splunk search` commands. Shell layer (imports Click)."""

from __future__ import annotations

import click

from . import output as out
from . import search as core
from .context import command


@click.group()
def search() -> None:
    """Run SPL searches."""


@search.command("run")
@click.argument("stdin_token", required=False, metavar="[-]")
@click.option("--query", default=None, help="SPL query string.")
@click.option("--file", "file_", type=click.File("r"), default=None, help="Read SPL from a file.")
@click.option("--earliest", default="-24h", show_default=True, help="Earliest time.")
@click.option("--latest", default="now", show_default=True, help="Latest time.")
@click.option("--max-rows", type=int, default=100, show_default=True, help="Max result rows.")
@click.option("--timeout", type=int, default=60, show_default=True, help="Search timeout (seconds).")
@command
def run(ctx, stdin_token, query, file_, earliest, latest, max_rows, timeout) -> None:
    """Run a bounded SPL search. Provide --query, --file, or '-' for stdin."""
    spl = out.resolve_query(query, file_, stdin_token)
    with ctx.client() as c:
        data = core.run_search(c, spl, earliest=earliest, latest=latest, max_rows=max_rows, timeout=timeout)
    out.emit(data, ctx.output_mode, ctx.meta())
