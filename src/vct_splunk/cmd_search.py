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
@click.option(
    "--max-rows",
    # IntRange(min=1) rejects 0 and negative values during argument parsing. This
    # guard matters because the value is forwarded to Splunk's ``count``
    # parameter, where ``count=0`` means "return *every* matching event" — the
    # opposite of the safe, bounded search this command promises.
    type=click.IntRange(min=1),
    default=100,
    show_default=True,
    help="Max result rows (must be >= 1).",
)
@click.option("--timeout", type=int, default=60, show_default=True, help="Search timeout (seconds).")
@command
def run(ctx, stdin_token, query, file_, earliest, latest, max_rows, timeout) -> None:
    """Run a bounded SPL search. Provide --query, --file, or '-' for stdin.

    Under ``--dry-run`` the search is **not** executed: the request that would be
    sent is printed instead. Running a search creates a server-side job and
    consumes resources, so previewing it (rather than silently executing it)
    keeps ``--dry-run`` honest for an automated caller.
    """
    spl = out.resolve_query(query, file_, stdin_token)

    if ctx.dry_run:
        # Short-circuit before any network call. We mirror the shape of the
        # write-preview the client returns for mutations, so ``--dry-run`` looks
        # consistent across commands, while sending nothing to Splunk. The body
        # is built by the same helper the real request uses, so the preview can't
        # drift from what would actually be sent.
        preview = {
            "dry_run": True,
            "request": {
                "method": "POST",
                "path": core.JOBS_PATH,
                "body": core.build_search_payload(
                    spl, earliest=earliest, latest=latest, max_rows=max_rows
                ),
            },
            "target": ctx.meta()["target"],
        }
        out.emit(preview, ctx.output_mode, ctx.meta())
        return

    with ctx.client() as c:
        data = core.run_search(c, spl, earliest=earliest, latest=latest, max_rows=max_rows, timeout=timeout)
    out.emit(data, ctx.output_mode, ctx.meta())
