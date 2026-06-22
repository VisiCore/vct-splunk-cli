from __future__ import annotations

import httpx
from click.testing import CliRunner

from vct_splunk.cli import cli
from vct_splunk.core import search


def test_normalize_spl_prefixes_bare_query():
    assert search.normalize_spl("index=_internal") == "search index=_internal"


def test_normalize_spl_leaves_search_and_generating_commands():
    assert search.normalize_spl("search index=_internal") == "search index=_internal"
    assert search.normalize_spl("| metadata type=sourcetypes") == "| metadata type=sourcetypes"


def test_normalize_spl_handles_non_space_whitespace():
    # A tab after `search` must not be double-prefixed into "search search\t...".
    assert search.normalize_spl("search\tindex=_internal") == "search\tindex=_internal"


def test_build_search_payload_is_bounded_oneshot():
    payload = search.build_search_payload(
        "index=_internal", earliest="-1h", latest="now", max_rows=5
    )
    assert payload["exec_mode"] == "oneshot"
    assert payload["count"] == 5
    assert payload["search"] == "search index=_internal"
    assert payload["earliest_time"] == "-1h"


def test_run_search_reports_count_and_truncation(client_for):
    rows = [{"a": 1}, {"a": 2}]

    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path.endswith("/services/search/jobs")
        return httpx.Response(200, json={"results": rows})

    out = search.run_search(client_for(handler), "index=_internal", max_rows=2)
    assert out["count"] == 2
    assert out["truncated"] is True  # got max_rows back -> the cap was hit
    assert out["results"] == rows


def test_search_run_dry_run_previews_without_executing():
    result = CliRunner().invoke(
        cli, ["search", "run", "--query", "index=_internal", "--dry-run", "--output", "json"]
    )
    assert result.exit_code == 0
    assert '"dry_run": true' in result.output
    assert '"exec_mode": "oneshot"' in result.output
