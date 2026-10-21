from __future__ import annotations

import json

import pytest

from vct_splunk.output import formatter as out
from vct_splunk.utils.errors import TransportError, UsageError


def test_resolve_mode_explicit():
    assert out.resolve_mode("json", False) == "json"
    assert out.resolve_mode(None, True) == "table"


def test_resolve_mode_defaults_by_tty(monkeypatch):
    # No explicit choice: a terminal gets a table, a pipe gets JSON.
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    assert out.resolve_mode(None, False) == "table"
    monkeypatch.setattr("sys.stdout.isatty", lambda: False)
    assert out.resolve_mode(None, False) == "json"


def test_table_empty_list_says_no_results(capsys):
    out.emit([], "table")
    assert "(no results)" in capsys.readouterr().out


def test_emit_json_envelope(capsys):
    out.emit([{"a": 1}], "json", {"target": "splunk.test"})
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["data"] == [{"a": 1}]
    assert parsed["meta"]["target"] == "splunk.test"


def test_fail_redacts_cloud_target_in_message_and_details(monkeypatch, capsys):
    target = "https://acme-test.splunkcloud.com:8089"
    monkeypatch.setenv("VCT_SPLUNK_REDACT_TARGET", "yes")

    with pytest.raises(SystemExit) as exc_info:
        out.fail(TransportError(f"Could not reach {target}", details={"request_url": target}))

    assert exc_info.value.code == 1
    rendered = capsys.readouterr().err
    payload = json.loads(rendered)
    assert "acme-test" not in rendered
    assert payload["error"]["message"] == "Could not reach https://<redacted>.splunkcloud.com:8089"
    assert payload["error"]["details"]["request_url"] == "https://<redacted>.splunkcloud.com:8089"


def test_emit_table(capsys):
    # A bare dict renders the same as a one-row list.
    out.emit({"name": "main", "size": 10}, "table")
    text = capsys.readouterr().out
    assert "NAME" in text and "main" in text


def test_resolve_query_stdin_token_must_be_dash():
    with pytest.raises(UsageError, match="stdin"):
        out.resolve_query(None, None, "not-a-dash")


def test_table_unions_keys_across_heterogeneous_rows(capsys):
    # A column present only in a later row must still appear (no silent drop).
    out.emit([{"a": 1}, {"b": 2}], "table")
    text = capsys.readouterr().out
    assert "A" in text and "B" in text
