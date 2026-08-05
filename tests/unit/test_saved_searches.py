"""Saved-search dispatch — the one saved-search operation the engine does not cover.

CRUD goes through the generic engine, which `test_resource_factory.py` proves
once for every spec. Dispatch is hand-written: it posts to a `/dispatch` suffix
and returns the search job id the caller polls.
"""

from __future__ import annotations

import httpx

from vct_splunk.core import saved_searches as ss


def test_dispatch_returns_sid(client_for):
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json={"sid": "sid99"})

    result = ss.dispatch_saved_search(client_for(handler), "nightly", owner="-", app="-")
    assert result["sid"] == "sid99"
    assert result["dispatched"] is True
