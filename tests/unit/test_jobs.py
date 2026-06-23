from __future__ import annotations

import httpx
import pytest

from vct_splunk.core import jobs
from vct_splunk.core.errors import NotFoundError


def test_list_jobs_normalizes(client_for):
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "entry": [
                    {
                        "name": "sid1",
                        "content": {"dispatchState": "DONE", "resultCount": 3},
                        "acl": {"owner": "admin", "app": "search"},
                    }
                ],
                "paging": {"total": 1},
            },
        )

    rows = jobs.list_jobs(client_for(handler))
    assert rows[0]["sid"] == "sid1"  # the SID is the entry name, not a content field
    assert rows[0]["dispatch_state"] == "DONE"
    assert rows[0]["owner"] == "admin"  # owner comes from the acl block


def test_get_job_missing_raises(client_for):
    with pytest.raises(NotFoundError):
        jobs.get_job(client_for(lambda req: httpx.Response(200, json={"entry": []})), "nope")


def test_cancel_job_posts_control_action(client_for):
    seen: dict[str, str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["method"] = req.method
        seen["path"] = req.url.path
        seen["body"] = req.content.decode()
        return httpx.Response(200, json={})

    jobs.cancel_job(client_for(handler), "sid1")
    assert seen["method"] == "POST"
    assert seen["path"] == "/services/search/jobs/sid1/control"
    assert "action=cancel" in seen["body"]


def test_cancel_job_dry_run_sends_nothing(client_for):
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={})

    result = jobs.cancel_job(client_for(handler, dry_run=True), "sid1")
    assert result["dry_run"] is True
    assert calls["n"] == 0
