from __future__ import annotations

from collections.abc import Callable
from typing import Any

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
    # Checks ship as versioned data, surfaced as its own verdict.
    assert verdicts["checks_version"]["evidence"] == health.HEALTH_CHECKS_VERSION


def _resource_handler(content: dict[str, Any]) -> Callable[[httpx.Request], httpx.Response]:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"entry": [{"content": content}]})

    return handler


def test_resource_usage_high_cpu_warns(client_for):
    handler = _resource_handler(
        {"cpu_system_pct": "60.0", "cpu_user_pct": "45.0", "mem": "16000", "mem_used": "4000"}
    )
    verdicts = {v.check: v for v in health._resource_usage(client_for(handler))}
    assert verdicts["resource_cpu"].finding == "warn"  # 105% > 90% threshold
    assert verdicts["resource_memory"].finding == "pass"  # 25% used


def test_resource_usage_normal_passes(client_for):
    handler = _resource_handler(
        {"cpu_system_pct": "5.0", "cpu_user_pct": "10.0", "mem": "16000", "mem_used": "4000"}
    )
    verdicts = {v.check: v for v in health._resource_usage(client_for(handler))}
    assert verdicts["resource_cpu"].finding == "pass"
    assert verdicts["resource_memory"].finding == "pass"


def test_disk_space_low_free_warns(client_for):
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "entry": [
                    {"content": {"mount_point": "/opt", "capacity": "1000", "free": "50"}},
                    {"content": {"mount_point": "/var", "capacity": "1000", "free": "800"}},
                ]
            },
        )

    verdicts = {v.check: v for v in health._disk_space(client_for(handler))}
    assert verdicts["disk:/opt"].finding == "warn"  # 5% free < 10% threshold
    assert verdicts["disk:/var"].finding == "pass"  # 80% free


def test_internal_errors_high_count_warns(client_for):
    # error_count comes back from Splunk as a string; the check must coerce it.
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": [{"error_count": "500"}]})

    verdicts = {v.check: v for v in health._internal_errors(client_for(handler))}
    assert verdicts["internal_errors"].finding == "warn"  # 500 > 100 threshold


def test_internal_errors_low_count_passes(client_for):
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": [{"error_count": "3"}]})

    verdicts = {v.check: v for v in health._internal_errors(client_for(handler))}
    assert verdicts["internal_errors"].finding == "pass"


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
