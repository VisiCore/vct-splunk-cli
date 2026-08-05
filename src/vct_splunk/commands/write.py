"""The one shared write path for every mutation. Shell layer.

Every gated write -- hand-written or factory-generated -- runs through
:func:`do_write`, so target resolution, the confirmation gate, and audit logging
live in exactly one place.

This function is also the seam for the larger write-safety framework (#12):
deferred pieces such as plan tokens, optimistic concurrency, and a freeze-writes
kill switch would all belong *inside* it. Add each only when a real second
writer needs it; today the call sites need exactly the gate + audit below.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from ..core import audit
from ..core.client import SplunkClient, config_from_env
from ..core.errors import UnsupportedBackendError
from . import output as out


def do_write(
    ctx: Any,
    *,
    action: str,
    audit_event: dict[str, Any],
    run: Callable[[SplunkClient], dict[str, Any]],
    target: str | None = None,
) -> dict[str, Any]:
    """Run one gated mutation: confirm it, execute it, and audit it.

    Resolves the target up front (so a missing ``SPLUNK_URL`` / ``SPLUNK_TOKEN``
    fails before we prompt), gates the write via :func:`output.confirm_write`
    (dry-run / ``--yes`` / non-interactive fail-fast), runs ``run(client)``, and
    appends an audit record for any real (non-dry-run) write.

    Args:
        ctx: The command :class:`~vct_splunk.commands.context.Ctx`.
        action: A human phrase for the prompt, e.g. ``"create index 'web'"``.
        audit_event: Fields to record on a real write; ``target`` is added here.
        run: Callable given an open client, returning the operation result.
        target: The Splunk URL; resolved from the environment when omitted.

    Returns:
        The operation result, ready for :func:`output.emit`.
    """
    # audit_event["action"] is "<resource>.<verb>", e.g. "index.create".
    resource, _, verb = str(audit_event.get("action", "")).partition(".")
    refuse_cloud_write(ctx, resource, verb)
    target = _safe_target(
        target or config_from_env(ctx.base_url, profile=getattr(ctx, "profile", None)).base_url
    )
    out.confirm_write(ctx, action, target)
    with ctx.client() as c:
        result = run(c)
    if not (isinstance(result, dict) and result.get("dry_run")):
        audit.record({**audit_event, "target": target})
    return result


def refuse_cloud_write(ctx: Any, resource: str, verb: str) -> None:
    """Stop a mutation aimed at a Splunk Cloud stack, before anything else runs.

    Writes are Enterprise-only this release. :func:`do_write` calls this, which
    is enough for a command that reaches the gate directly. A command that first
    resolves a namespace calls it earlier as well, so a Cloud target is told that
    writes are unsupported rather than being asked for an ``--app`` that would
    not have helped.
    """
    if getattr(ctx, "backend", "enterprise") == "cloud":
        raise UnsupportedBackendError(resource or "this resource", verb or "write", "cloud")


def _safe_target(target: str) -> str:
    """Remove URL credentials and non-target components before display or audit."""
    parsed = urlsplit(target)
    if not parsed.hostname:
        return target
    host = parsed.hostname
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    try:
        if parsed.port is not None:
            host = f"{host}:{parsed.port}"
    except ValueError:
        return urlunsplit((parsed.scheme, host, parsed.path, "", ""))
    return urlunsplit((parsed.scheme, host, parsed.path, "", ""))
