from __future__ import annotations

import json

from vct_splunk.commands import output as out


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


def test_table_single_dict_renders_one_row(capsys):
    out.emit({"name": "main", "disabled": False}, "table")
    text = capsys.readouterr().out
    assert "NAME" in text and "main" in text


def test_emit_json_envelope(capsys):
    out.emit([{"a": 1}], "json", {"target": "splunk.test"})
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["data"] == [{"a": 1}]
    assert parsed["meta"]["target"] == "splunk.test"


def test_emit_table(capsys):
    out.emit([{"name": "main", "size": 10}], "table")
    text = capsys.readouterr().out
    assert "NAME" in text and "main" in text


def test_table_unions_keys_across_heterogeneous_rows(capsys):
    # A column present only in a later row must still appear (no silent drop).
    out.emit([{"a": 1}, {"b": 2}], "table")
    text = capsys.readouterr().out
    assert "A" in text and "B" in text
