"""Tests for the shared write path, do_write (#12).

One test per gate: dry-run sends nothing and skips the audit; a real write is
audited with its target; a non-interactive write without --yes is refused.
"""

from __future__ import annotations

import httpx
import pytest

from vct_splunk.commands.write import do_write
from vct_splunk.core.client import ClientConfig, SplunkClient
from vct_splunk.core.errors import UsageError


class _Ctx:
    """Minimal Ctx stand-in: do_write only needs base_url, dry_run, yes, client()."""

    def __init__(self, *, dry_run: bool = False, yes: bool = False) -> None:
        self.base_url = "https://splunk.test:8089"
        self.dry_run = dry_run
        self.yes = yes

    def client(self) -> SplunkClient:
        cfg = ClientConfig(base_url=self.base_url, token="T", dry_run=self.dry_run)
        return SplunkClient(
            cfg, transport=httpx.MockTransport(lambda req: httpx.Response(200, json={}))
        )


def test_do_write_dry_run_skips_audit_and_returns_preview(monkeypatch, tmp_path):
    monkeypatch.setenv("SPLUNK_TOKEN", "T")
    audit_file = tmp_path / "audit.log"
    monkeypatch.setenv("VCT_SPLUNK_AUDIT", str(audit_file))
    result = do_write(
        _Ctx(dry_run=True),
        action="do thing",
        audit_event={"action": "x"},
        run=lambda c: {"dry_run": True, "request": {}},
    )
    assert result["dry_run"] is True
    assert not audit_file.exists()  # a dry run records nothing


def test_do_write_records_audit_on_real_write(monkeypatch, tmp_path):
    monkeypatch.setenv("SPLUNK_TOKEN", "T")
    audit_file = tmp_path / "audit.log"
    monkeypatch.setenv("VCT_SPLUNK_AUDIT", str(audit_file))
    result = do_write(
        _Ctx(yes=True),  # --yes bypasses the prompt non-interactively
        action="do thing",
        audit_event={"action": "index.create", "name": "web"},
        run=lambda c: {"name": "web"},
    )
    assert result == {"name": "web"}
    contents = audit_file.read_text()
    assert "index.create" in contents
    assert "https://splunk.test:8089" in contents  # target is recorded


def test_do_write_refuses_without_yes_noninteractive(monkeypatch, tmp_path):
    monkeypatch.setenv("SPLUNK_TOKEN", "T")
    monkeypatch.setenv("VCT_SPLUNK_AUDIT", str(tmp_path / "audit.log"))
    with pytest.raises(UsageError):
        do_write(
            _Ctx(),  # not dry-run, not --yes -> refuse rather than hang
            action="do thing",
            audit_event={"action": "x"},
            run=lambda c: {"name": "x"},
        )


def test_audit_falls_back_to_xdg_state_home(monkeypatch, tmp_path):
    from vct_splunk.core import audit

    monkeypatch.delenv("VCT_SPLUNK_AUDIT", raising=False)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    written = audit.record({"action": "index.create"})
    assert written == str(tmp_path / "vct-splunk" / "audit.log")
    assert "index.create" in (tmp_path / "vct-splunk" / "audit.log").read_text()
