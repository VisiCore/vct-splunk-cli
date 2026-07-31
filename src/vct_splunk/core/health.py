"""Health checks over native REST endpoints. Click-free core.

Each verdict reports three independent dimensions so "unknown" never silently reads
as "healthy":
  applicability: applicable | not_applicable | unknown
  execution:     completed | error | timeout | permission_denied
  finding:       pass | warn | fail | na
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

from .client import SplunkClient
from .errors import AuthError, NotFoundError, SplunkError
from .search import run_search

_FINDING = {"green": "pass", "yellow": "warn", "red": "fail"}

HEALTH_CHECKS_VERSION = "1"

# Calibration knobs for the resource/introspection checks. They are named module
# constants (not magic numbers) so they read as the single place to retune.
_CPU_WARN_PCT = 90.0  # warn when combined system+user CPU exceeds this percentage
_MEM_WARN_PCT = 90.0  # warn when used memory exceeds this percentage of total
_DISK_WARN_FREE_PCT = 10.0  # warn when a partition's free space drops below this
_ERROR_WARN_COUNT = 100  # warn when splunkd ERROR events in the window exceed this
_INTERNAL_ERROR_WINDOW = "15m"


@dataclass
class Verdict:
    check: str
    applicability: str
    execution: str
    finding: str
    evidence: str = ""


def check_health(client: SplunkClient) -> list[dict[str, Any]]:
    verdicts = [
        _reachable(client),
        *_splunkd(client),
        *_resource_usage(client),
        *_disk_space(client),
        *_internal_errors(client),
    ]
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
        return [_unavailable("splunkd_health", exc)]
    content = (body.get("entry") or [{}])[0].get("content", {})
    overall = content.get("health")
    if overall not in _FINDING:
        return [_unknown("splunkd_health", "missing or unrecognized overall health")]
    out = [
        Verdict(
            "splunkd_overall",
            "applicable",
            "completed",
            _FINDING[overall],
            f"health={overall}",
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


def _resource_usage(client: SplunkClient) -> list[Verdict]:
    """CPU and memory verdicts from host-wide introspection.

    Reads ``/services/server/status/resource-usage/hostwide`` and emits one CPU
    verdict (combined system+user) and one memory verdict (used / total). Both
    warn past their calibration thresholds, else pass. Any transport/API failure
    collapses into a single error verdict so a missing endpoint never crashes the
    rest of the report.
    """
    try:
        content = (
            client.get("/services/server/status/resource-usage/hostwide").get("entry") or [{}]
        )[0].get("content", {})
    except SplunkError as exc:
        return [_unavailable("resource_usage", exc)]

    cpu_system = _to_float(content.get("cpu_system_pct"))
    cpu_user = _to_float(content.get("cpu_user_pct"))
    load = _to_float(content.get("normalized_load_avg_1min"))
    if cpu_system is None or cpu_user is None:
        cpu = _unknown("resource_cpu", "missing or malformed CPU usage data")
    else:
        cpu_pct = cpu_system + cpu_user
        load_evidence = f", load_1min={load:.2f}" if load is not None else ""
        cpu = Verdict(
            "resource_cpu",
            "applicable",
            "completed",
            "warn" if cpu_pct > _CPU_WARN_PCT else "pass",
            f"cpu={cpu_pct:.1f}% (warn>{_CPU_WARN_PCT:g}%){load_evidence}",
        )

    mem_total = _to_float(content.get("mem"))
    mem_used = _to_float(content.get("mem_used"))
    if mem_total is None or mem_used is None or mem_total <= 0:
        mem = _unknown("resource_memory", "missing, malformed, or zero-total memory data")
    else:
        mem_pct = mem_used / mem_total * 100.0
        mem = Verdict(
            "resource_memory",
            "applicable",
            "completed",
            "warn" if mem_pct > _MEM_WARN_PCT else "pass",
            (
                f"mem={mem_pct:.1f}% used "
                f"({mem_used:.0f}/{mem_total:.0f} MB, warn>{_MEM_WARN_PCT:g}%)"
            ),
        )
    return [cpu, mem]


def _disk_space(client: SplunkClient) -> list[Verdict]:
    """One verdict per filesystem partition from ``partitions-space``.

    Each entry carries a ``mount_point`` with ``capacity`` and ``free`` (MB). A
    partition warns when its free percentage drops below the threshold. A failure
    to read the endpoint collapses into a single error verdict.
    """
    try:
        entries = client.get_collection("/services/server/status/partitions-space")
    except SplunkError as exc:
        return [_unavailable("disk_space", exc)]

    if not entries:
        return [_unknown("disk_space", "partition endpoint returned no data")]

    out: list[Verdict] = []
    for entry in entries:
        content = (entry or {}).get("content", {})
        mount = content.get("mount_point") or (entry or {}).get("name") or "?"
        capacity = _to_float(content.get("capacity"))
        free = _to_float(content.get("free"))
        if capacity is None or free is None or capacity <= 0:
            out.append(
                _unknown(
                    f"disk:{mount}",
                    "missing, malformed, or zero-capacity partition data",
                )
            )
            continue
        free_pct = free / capacity * 100.0
        evidence = (
            f"free={free_pct:.1f}% ({free:.0f}/{capacity:.0f} MB, warn<{_DISK_WARN_FREE_PCT:g}%)"
        )
        out.append(
            Verdict(
                f"disk:{mount}",
                "applicable",
                "completed",
                "warn" if free_pct < _DISK_WARN_FREE_PCT else "pass",
                evidence,
            )
        )
    return out


def _internal_errors(client: SplunkClient) -> list[Verdict]:
    """Recent splunkd ERROR-rate verdict via a clean-room SPL search.

    The SPL is written here from scratch (a plain ``stats count``) and is
    deliberately *not* derived from Splunk's proprietary Monitoring Console
    searches. It counts splunkd ERROR events in a short trailing window; the count
    warns past the threshold. ``error_count`` can arrive as a string, so it is
    coerced. A search failure collapses into a single error verdict.
    """
    try:
        body = run_search(
            client,
            "index=_internal sourcetype=splunkd log_level=ERROR | stats count as error_count",
            earliest=f"-{_INTERNAL_ERROR_WINDOW}",
            latest="now",
            max_rows=1,
        )
    except SplunkError as exc:
        return [_unavailable("internal_errors", exc)]

    results = body.get("results") or []
    if not results or not isinstance(results[0], dict):
        return [_unknown("internal_errors", "internal-error search returned no data")]
    count_value = _to_float(results[0].get("error_count"))
    if count_value is None or count_value < 0:
        return [_unknown("internal_errors", "internal-error count is missing or malformed")]
    count = int(count_value)
    return [
        Verdict(
            "internal_errors",
            "applicable",
            "completed",
            "warn" if count > _ERROR_WARN_COUNT else "pass",
            (
                f"{count} splunkd ERROR events in {_INTERNAL_ERROR_WINDOW} "
                f"(warn>{_ERROR_WARN_COUNT})"
            ),
        )
    ]


def _unknown(check: str, evidence: str) -> Verdict:
    """Return a neutral verdict for data whose health cannot be determined."""
    return Verdict(check, "unknown", "error", "na", evidence)


def _unavailable(check: str, exc: SplunkError) -> Verdict:
    """Describe an optional check that the target cannot or will not expose."""
    if isinstance(exc, NotFoundError):
        return Verdict(check, "not_applicable", "completed", "na", exc.message)
    if isinstance(exc, AuthError):
        return Verdict(check, "unknown", "permission_denied", "na", exc.message)
    return Verdict(check, "unknown", "error", "na", exc.message)


def _to_float(value: Any) -> float | None:
    """Coerce a Splunk numeric field, preserving missing or malformed input.

    Splunk returns numeric introspection fields as JSON strings (e.g. ``"42.5"``),
    so every threshold comparison routes through this instead of assuming a type.
    ``None`` distinguishes unknown data from a valid numeric zero.
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None
