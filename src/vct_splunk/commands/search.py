"""`splunk search` commands. Shell layer (imports Click)."""

from __future__ import annotations

import click

from ..core import jobs as jobs_core
from ..core import search as core
from . import output as out
from .context import command
from .write import do_write


@click.group()
def search() -> None:
    """Run SPL searches."""


@search.command("list")
@command
def list_(ctx) -> None:
    """List search jobs."""
    with ctx.client() as c:
        out.emit(jobs_core.list_jobs(c), ctx.output_mode, ctx.meta())


@search.command("get")
@click.argument("sid")
@command
def get(ctx, sid) -> None:
    """Show one search job by its SID."""
    with ctx.client() as c:
        out.emit(jobs_core.get_job(c, sid), ctx.output_mode, ctx.meta())


@search.command("cancel")
@click.argument("sid")
@command
def cancel(ctx, sid) -> None:
    """Cancel a running search job (frees its server resources). Gated write."""
    result = do_write(
        ctx,
        action=f"cancel search job '{sid}'",
        audit_event={"action": "search.cancel", "sid": sid},
        run=lambda c: jobs_core.cancel_job(c, sid),
    )
    out.emit(result, ctx.output_mode, ctx.meta())


@search.command("run")
@click.argument("stdin_token", required=False, metavar="[-]")
@click.option("--query", default=None, help="SPL query string.")
@click.option("--file", "file_", type=click.File("r"), default=None, help="Read SPL from a file.")
@click.option(
    "--earliest",
    default="-24h",
    show_default=True,
    help="Start of the search window (Splunk relative-time syntax).",
)
@click.option("--latest", default="now", show_default=True, help="End of the search window.")
@click.option(
    "--max-rows",
    # Must stay >= 1: the value feeds Splunk's ``count``, where 0 means
    # "return *every* matching event" — the opposite of a bounded search.
    type=click.IntRange(min=1),
    default=100,
    show_default=True,
    help="Max result rows (must be >= 1).",
)
@click.option(
    "--timeout",
    type=click.IntRange(min=1),
    default=60,
    show_default=True,
    help="Search timeout in seconds (must be >= 1).",
)
@click.option(
    "--export",
    "export_",
    is_flag=True,
    help="Stream from the export endpoint (no job is created), bounded by --max-rows.",
)
@command
def run(ctx, stdin_token, query, file_, earliest, latest, max_rows, timeout, export_) -> None:
    """Run a bounded SPL search. Provide --query, --file, or '-' for stdin.

    Under ``--dry-run`` the search is **not** executed: the request that would be
    sent is printed instead. A normal run uses a oneshot job; ``--export`` streams
    results straight from the export endpoint without creating a job. Either way
    the row cap keeps an automated caller from triggering an unbounded export.
    """
    spl = out.resolve_query(query, file_, stdin_token)
    # Pick the endpoint and payload builder once, so the dry-run preview and the
    # real request can never disagree.
    if export_:
        path = core.EXPORT_PATH
        body = core.build_export_payload(spl, earliest=earliest, latest=latest, max_rows=max_rows)
    else:
        path = core.JOBS_PATH
        body = core.build_search_payload(spl, earliest=earliest, latest=latest, max_rows=max_rows)

    if ctx.dry_run:
        # Short-circuit before any network call. We mirror the shape of the
        # write-preview the client returns for mutations, so ``--dry-run`` looks
        # consistent across commands while sending nothing to Splunk.
        preview = {
            "dry_run": True,
            "request": {"method": "POST", "path": path, "body": body},
            "target": ctx.meta()["target"],
        }
        out.emit(preview, ctx.output_mode, ctx.meta())
        return

    with ctx.client() as c:
        if export_:
            data = core.run_export(
                c, spl, earliest=earliest, latest=latest, max_rows=max_rows, timeout=timeout
            )
        else:
            data = core.run_search(
                c, spl, earliest=earliest, latest=latest, max_rows=max_rows, timeout=timeout
            )
    out.emit(data, ctx.output_mode, ctx.meta())
