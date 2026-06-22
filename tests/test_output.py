from __future__ import annotations

import json

from vct_splunk import output as out


def test_resolve_mode_explicit():
    assert out.resolve_mode("json", False) == "json"
    assert out.resolve_mode(None, True) == "table"


def test_emit_json_envelope(capsys):
    out.emit([{"a": 1}], "json", {"target": "splunk.test"})
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["data"] == [{"a": 1}]
    assert parsed["meta"]["target"] == "splunk.test"


def test_emit_table(capsys):
    out.emit([{"name": "main", "size": 10}], "table")
    text = capsys.readouterr().out
    assert "NAME" in text and "main" in text
