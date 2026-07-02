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


def test_health_red_maps_to_fail(client_for):
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/server/info"):
            return httpx.Response(200, json={"entry": [{"content": {}}]})
        return httpx.Response(200, json={"entry": [{"content": {"health": "red"}}]})

    verdicts = {v["check"]: v for v in health.check_health(client_for(handler))}
    assert verdicts["splunkd_overall"]["finding"] == "fail"


def test_health_unreachable_server_is_fail_not_crash(client_for):
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    verdicts = {v["check"]: v for v in health.check_health(client_for(handler))}
    reachable = verdicts["server_reachable"]
    assert (reachable["execution"], reachable["finding"]) == ("error", "fail")


def test_health_endpoint_error_reports_unknown_applicability(client_for):
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/server/info"):
            return httpx.Response(200, json={"entry": [{"content": {"version": "9.4"}}]})
        # The health endpoint itself failing must read as unknown/error, never
        # silently as healthy.
        return httpx.Response(500, json={})

    verdicts = {v["check"]: v for v in health.check_health(client_for(handler))}
    splunkd = verdicts["splunkd_health"]
    assert (splunkd["applicability"], splunkd["execution"], splunkd["finding"]) == (
        "unknown",
        "error",
        "fail",
    )
