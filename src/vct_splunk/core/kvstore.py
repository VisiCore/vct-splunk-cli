"""KV Store data records: a namespaced JSON document store. Click-free core.

KV Store *data* is unlike the rest of the REST API. Records live under
``/servicesNS/<owner>/<app>/storage/collections/data/<collection>`` and are a
plain JSON document store: a write sends a JSON body (``Content-Type:
application/json``) and a read returns a JSON array (a collection) or object
(one record) -- never the Splunk ``entry[].content`` envelope. The collection
*schema* is a separate, CRUD-shaped resource (the ``kvstore-collection`` factory
group); this module only touches the records inside a collection.

Every call requires an explicit app and defaults to owner ``nobody``.
"""

from __future__ import annotations

from typing import Any

from .client import SplunkClient
from .errors import NotFoundError
from .namespace import ns_path
from .path import path_segment

_DATA = "storage/collections/data"


def _path(collection: str, *, owner: str, app: str, key: str | None = None) -> str:
    suffix = f"{_DATA}/{path_segment(collection, label='collection')}"
    if key is not None:
        suffix += f"/{path_segment(key, label='record key')}"
    return ns_path(suffix, owner=owner, app=app)


def list_records(
    client: SplunkClient,
    collection: str,
    *,
    owner: str,
    app: str,
    query: str | None = None,
    limit: int | None = None,
) -> Any:
    """List records in a collection, returning the JSON array as-is.

    ``query`` is a MongoDB-style JSON filter (passed through verbatim) and
    ``limit`` caps the number of records; both are sent only when given.
    """
    params: dict[str, Any] = {}
    if query is not None:
        params["query"] = query
    if limit is not None:
        params["limit"] = limit
    return client.get(_path(collection, owner=owner, app=app), params or None)


def get_record(client: SplunkClient, collection: str, key: str, *, owner: str, app: str) -> Any:
    """Return one record by its ``_key``.

    Raises:
        NotFoundError: If the record does not exist (a 404 already maps to
            NotFoundError in the client; an empty body is treated the same).
    """
    record = client.get(_path(collection, key=key, owner=owner, app=app))
    if not record:
        raise NotFoundError(f"Record {key!r} not found in collection {collection!r}.")
    return record


def insert_record(
    client: SplunkClient, collection: str, document: dict[str, Any], *, owner: str, app: str
) -> Any:
    """Insert a record (JSON body). Splunk returns ``{"_key": "..."}``."""
    return client.write_json("POST", _path(collection, owner=owner, app=app), document)


def update_record(
    client: SplunkClient,
    collection: str,
    key: str,
    document: dict[str, Any],
    *,
    owner: str,
    app: str,
) -> Any:
    """Replace the record at ``key`` with ``document`` (JSON body)."""
    return client.write_json("POST", _path(collection, key=key, owner=owner, app=app), document)


def delete_record(client: SplunkClient, collection: str, key: str, *, owner: str, app: str) -> Any:
    """Delete one record by its ``_key``."""
    return client.write("DELETE", _path(collection, key=key, owner=owner, app=app), {})


def delete_all(client: SplunkClient, collection: str, *, owner: str, app: str) -> Any:
    """Delete *every* record in the collection (the schema is left intact)."""
    return client.write("DELETE", _path(collection, owner=owner, app=app), {})
