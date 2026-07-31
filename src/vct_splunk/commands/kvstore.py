"""`splunk kvstore` commands for KV Store *data records*. Shell layer (imports Click).

This group operates on the records *inside* a KV Store collection -- a JSON
document store. The collection *schema* (creating the collection and its fields)
is a separate group, ``kvstore-collection``.

Every operation requires an explicit ``--app`` (or ``$SPLUNK_APP``) and defaults
to owner ``nobody`` because Splunk does not support wildcard KV data namespaces.
"""

from __future__ import annotations

import json
from typing import Any

import click

from ..core import kvstore as core
from ..core.errors import UsageError
from ..core.namespace import resolve_ns
from ..core.path import path_segment
from . import output as out
from .context import command
from .write import do_write


@click.group(name="kvstore")
def kvstore() -> None:
    """KV Store data records, a JSON document store (schema lives in 'kvstore-collection')."""


def _parse_doc(data: str) -> dict[str, Any]:
    """Parse a ``--data`` JSON object, raising a clean UsageError on bad input."""
    try:
        doc = json.loads(data)
    except json.JSONDecodeError as exc:
        raise UsageError(f"--data is not valid JSON: {exc}") from exc
    if not isinstance(doc, dict):
        raise UsageError("--data must be a JSON object (a single record).")
    return doc


@kvstore.command("records")
@click.argument("collection")
@click.option("--query", default=None, help="JSON filter (MongoDB-style) to match records.")
@click.option("--limit", type=int, default=None, help="Maximum number of records to return.")
@command
def records(ctx, collection, query, limit) -> None:
    """List records in a collection (use --query/--limit to narrow)."""
    path_segment(collection, label="collection")
    owner, app = resolve_ns(ctx.owner, ctx.app, for_write=True)
    with ctx.client() as c:
        data = core.list_records(c, collection, owner=owner, app=app, query=query, limit=limit)
    out.emit(data, ctx.output_mode, ctx.meta())


@kvstore.command("get")
@click.argument("collection")
@click.argument("key")
@command
def get(ctx, collection, key) -> None:
    """Show one record by its _key."""
    path_segment(collection, label="collection")
    path_segment(key, label="record key")
    owner, app = resolve_ns(ctx.owner, ctx.app, for_write=True)
    with ctx.client() as c:
        data = core.get_record(c, collection, key, owner=owner, app=app)
    out.emit(data, ctx.output_mode, ctx.meta())


@kvstore.command("insert")
@click.argument("collection")
@click.option("--data", "data", required=True, help="The record as a JSON object.")
@command
def insert(ctx, collection, data) -> None:
    """Insert a record (JSON document). Gated write; requires an app."""
    path_segment(collection, label="collection")
    owner, app = resolve_ns(ctx.owner, ctx.app, for_write=True)
    document = _parse_doc(data)
    result = do_write(
        ctx,
        action=f"insert a record into '{collection}' in app '{app}'",
        audit_event={"action": "kvstore.insert", "collection": collection, "app": app},
        run=lambda c: core.insert_record(c, collection, document, owner=owner, app=app),
    )
    out.emit(result, ctx.output_mode, ctx.meta())


@kvstore.command("update")
@click.argument("collection")
@click.argument("key")
@click.option("--data", "data", required=True, help="The replacement record as a JSON object.")
@command
def update(ctx, collection, key, data) -> None:
    """Replace a record by its _key (JSON document). Gated write; requires an app."""
    path_segment(collection, label="collection")
    path_segment(key, label="record key")
    owner, app = resolve_ns(ctx.owner, ctx.app, for_write=True)
    document = _parse_doc(data)
    result = do_write(
        ctx,
        action=f"update record '{key}' in '{collection}' in app '{app}'",
        audit_event={
            "action": "kvstore.update",
            "collection": collection,
            "key": key,
            "app": app,
        },
        run=lambda c: core.update_record(c, collection, key, document, owner=owner, app=app),
    )
    out.emit(result, ctx.output_mode, ctx.meta())


@kvstore.command("delete")
@click.argument("collection")
@click.argument("key")
@command
def delete(ctx, collection, key) -> None:
    """Delete one record by its _key. Gated write; requires an app."""
    path_segment(collection, label="collection")
    path_segment(key, label="record key")
    owner, app = resolve_ns(ctx.owner, ctx.app, for_write=True)
    result = do_write(
        ctx,
        action=f"delete record '{key}' from '{collection}' in app '{app}'",
        audit_event={
            "action": "kvstore.delete",
            "collection": collection,
            "key": key,
            "app": app,
        },
        run=lambda c: core.delete_record(c, collection, key, owner=owner, app=app),
    )
    out.emit(result, ctx.output_mode, ctx.meta())


@kvstore.command("purge")
@click.argument("collection")
@command
def purge(ctx, collection) -> None:
    """Delete ALL records in a collection (the schema is kept). Gated write; requires an app."""
    path_segment(collection, label="collection")
    owner, app = resolve_ns(ctx.owner, ctx.app, for_write=True)
    result = do_write(
        ctx,
        action=f"delete ALL records in '{collection}' in app '{app}'",
        audit_event={"action": "kvstore.purge", "collection": collection, "app": app},
        run=lambda c: core.delete_all(c, collection, owner=owner, app=app),
    )
    out.emit(result, ctx.output_mode, ctx.meta())
