"""Health checks over native REST endpoints. Click-free core.

Each verdict reports three independent dimensions so "unknown" never silently reads
as "healthy":
  applicability: applicable | not_applicable | unknown
  execution:     completed | error | timeout | permission_denied
  finding:       pass | warn | fail | na
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .client import SplunkClient
from .errors import SplunkError

_FINDING = {"green": "pass", "yellow": "warn", "red": "fail"}


@dataclass
class Verdict:
    check: str
    applicability: str
    execution: str
    finding: str
    evidence: str = ""


def check_health(client: SplunkClient) -> list[dict[str, Any]]:
    verdicts = [_reachable(client), *_splunkd(client)]
    return [asdict(v) for v in verdicts]


def _reachable(client: SplunkClient) -> Verdict:
    try:
        content = (client.get("/services/server/info").get("entry") or [{}])[0].get("content", {})
    except SplunkError as exc:
        return Verdict("server_reachable", "applicable", "error", "fail", exc.message)
    return Verdict(
        "server_reachable",
        "applicable",
        "completed",
        "pass",
        f"version {content.get('version')} ({content.get('serverName')})",
    )


def _splunkd(client: SplunkClient) -> list[Verdict]:
    try:
        body = client.get("/services/server/health/splunkd/details")
    except SplunkError as exc:
        return [Verdict("splunkd_health", "unknown", "error", "fail", exc.message)]
    content = (body.get("entry") or [{}])[0].get("content", {})
    out = [
        Verdict(
            "splunkd_overall",
            "applicable",
            "completed",
            _FINDING.get(content.get("health"), "warn"),
            f"health={content.get('health')}",
        )
    ]
    for name, feature in sorted((content.get("features") or {}).items()):
        health = (feature or {}).get("health")
        if health:
            out.append(
                Verdict(
                    f"feature:{name}",
                    "applicable",
                    "completed",
                    _FINDING.get(health, "warn"),
                    f"health={health}",
                )
            )
    return out
