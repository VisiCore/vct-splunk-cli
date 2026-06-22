from __future__ import annotations

import httpx

from vct_splunk.core import health


def test_health_maps_findings(client_for):
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/server/info"):
            return httpx.Response(
                200, json={"entry": [{"content": {"version": "9.4", "serverName": "sh1"}}]}
            )
        return httpx.Response(
            200,
            json={
                "entry": [
                    {
                        "content": {
                            "health": "green",
                            "features": {
                                "Indexing": {"health": "yellow"},
                                "Search": {"health": "green"},
                            },
                        }
                    }
                ]
            },
        )

    verdicts = {v["check"]: v for v in health.check_health(client_for(handler))}
    assert verdicts["server_reachable"]["finding"] == "pass"
    assert verdicts["splunkd_overall"]["finding"] == "pass"
    assert verdicts["feature:Indexing"]["finding"] == "warn"
    assert verdicts["feature:Indexing"]["applicability"] == "applicable"
