"""The one shared write path for every mutation. Shell layer.

Every gated write -- hand-written or factory-generated -- runs through
:func:`do_write`, so target resolution, both write-enable gates, backend
routing, the confirmation gate, and audit logging all live in exactly one
place.

This function is also the seam for the larger write-safety framework (#12):
deferred pieces such as plan tokens, optimistic concurrency, and a freeze-writes
kill switch would all belong *inside* it. Add each only when a real second
writer needs it; today the call sites need exactly the gates + audit below.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from ..api.acs.client import AcsClient, acs_config_from_env
from ..api.acs.operations import cloud_write
from ..config.loader import _resolve_target, load_config
from ..output import formatter as out
from ..utils import audit
from ..utils.backends import cloud_stack_from_url
from ..utils.errors import UnsupportedBackendError, UsageError
from ..utils.redact import public_target, safe_target
from .dispatch import has_cloud_write

#: Opt-in for ANY real mutation, on any backend. Never a CLI flag -- a saved
#: command line must not be able to enable a write. ``--dry-run`` needs neither
#: this nor :data:`CLOUD_WRITE_ENV`: a preview sends nothing regardless, so
#: :func:`do_write` skips both checks for it.
ENABLE_WRITES_ENV = "SPLUNK_ENABLE_WRITES"

#: Additional opt-in required, on top of :data:`ENABLE_WRITES_ENV`, for a real
#: write against a Splunk Cloud target. Never a CLI flag either. See
#: :func:`refuse_cloud_write`.
CLOUD_WRITE_ENV = "SPLUNK_CLOUD_WRITE"


def do_write(
    ctx: Any,
    *,
    action: str,
    audit_event: dict[str, Any],
    run: Callable[[Any], dict[str, Any]],
    target: str | None = None,
    name: str | None = None,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run one gated mutation: confirm it, execute it, and audit it.

    Refuses outright unless :data:`ENABLE_WRITES_ENV` is set (every backend,
    real writes only -- ``--dry-run`` sends nothing regardless, so it is exempt)
    and, on a Cloud target, unless the object is one of the three ACS-writable
    resources and :data:`CLOUD_WRITE_ENV` is also set. That second check is
    enforced even for a preview -- see :func:`refuse_cloud_write`. Then resolves
    the target up front (so a missing ``SPLUNK_URL`` / credential
    fails before we prompt), gates the write via :func:`output.confirm_write`
    (dry-run / ``--yes`` / non-interactive fail-fast), runs the operation on the
    backend-appropriate client, and appends an audit record for any real
    (non-dry-run) write.

    Args:
        ctx: The command :class:`~vct_splunk.commands.context.Ctx`.
        action: A human phrase for the prompt, e.g. ``"create index 'web'"``.
        audit_event: Fields to record on a real write; ``target`` is added
            here. ``audit_event["action"]`` is ``"<resource>.<verb>"``, e.g.
            ``"index.create"``.
        run: Callable given an open Enterprise ``SplunkClient``, returning the
            operation result. Not called for a Cloud write -- see ``name`` and
            ``body``.
        target: The Splunk URL; resolved from the environment when omitted.
        name: The object name, needed only for a Cloud write. The REST path
            already has its name closed over inside ``run``.
        body: The ACS JSON body for a Cloud create/update. Built by the caller
            -- it needs the resource's own field mapping, which this module
            does not have. Ignored for delete and on Enterprise.

    Returns:
        The operation result, ready for :func:`output.emit`.
    """
    resource, _, verb = str(audit_event.get("action", "")).partition(".")
    refuse_cloud_write(ctx, resource, verb)
    if not ctx.dry_run:
        _require_writes_enabled(resource, verb)
    backend = getattr(ctx, "backend", "enterprise")
    if target is None:
        if backend == "cloud":
            # A Cloud write authenticates to ACS, not splunkd, so resolving the
            # target must not go through `load_config` -- that function demands
            # a splunkd credential (SPLUNK_TOKEN et al.) this path never needs.
            target = _resolve_target(ctx.base_url, getattr(ctx, "profile", None))[0].base_url
        else:
            target = load_config(ctx.base_url, profile=getattr(ctx, "profile", None)).base_url
    out.confirm_write(ctx, action, public_target(target))
    if backend == "cloud":
        stack = cloud_stack_from_url(ctx.base_url)
        config = acs_config_from_env(stack, write=True)
        config.dry_run = ctx.dry_run
        with AcsClient(config) as c:
            result = cloud_write(c, resource, verb, name or "", body)
    else:
        with ctx.client() as c:
            result = run(c)
    if not (isinstance(result, dict) and result.get("dry_run")):
        audit.record({**audit_event, "target": safe_target(target)})
    return result


def refuse_cloud_write(ctx: Any, resource: str, verb: str) -> None:
    """Stop a Cloud mutation with no ACS route; gate the rest behind opt-in.

    Two independent checks, in order, both enforced unconditionally --
    dry-run or not:

    1. **Capability**. Only create/update/delete for index, role, and
       hec-token (see :func:`vct_splunk.commands.dispatch.has_cloud_write`)
       exist on Cloud at all; every other Cloud mutation -- including
       enable/disable on those same three resources -- has no route to opt
       into, so this always raises.
    2. **Opt-in** (:data:`CLOUD_WRITE_ENV`). Unlike the top-level
       :data:`ENABLE_WRITES_ENV` gate in :func:`do_write` (which a preview
       skips, since it sends nothing regardless), this one is a capability
       fact as much as a safety switch: even a Cloud *preview* needs to prove
       the object is one of the three ACS-writable resources, so ``--dry-run``
       does not exempt it.

    :func:`do_write` calls this, which is enough for a command that reaches the
    gate directly. A command that first resolves a namespace calls it earlier
    as well, so a Cloud target is told writes are unsupported rather than
    asked for an ``--app`` that would not have helped.
    """
    if getattr(ctx, "backend", "enterprise") != "cloud":
        return
    if not has_cloud_write(resource, verb):
        raise UnsupportedBackendError(resource or "this resource", verb or "write", "cloud")
    if os.environ.get(CLOUD_WRITE_ENV) != "true":
        raise UnsupportedBackendError(resource or "this resource", verb or "write", "cloud")


def _require_writes_enabled(resource: str, verb: str) -> None:
    """Refuse a real (non-dry-run) mutation unless :data:`ENABLE_WRITES_ENV` is set.

    Every backend, always -- there is no CLI flag, so a saved command line can
    never enable a write. Only :func:`do_write` calls this, and only when
    ``ctx.dry_run`` is False; a preview sends nothing and needs no opt-in.
    """
    if os.environ.get(ENABLE_WRITES_ENV) == "true":
        return
    raise UsageError(
        f"Writes are disabled by default. Set {ENABLE_WRITES_ENV}=true to allow "
        f"`{resource} {verb}` (there is no CLI flag for this)."
    )
