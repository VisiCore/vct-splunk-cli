"""Unit tests for config-file profiles (#13)."""

from __future__ import annotations

import os

import pytest

from vct_splunk.core.errors import UsageError
from vct_splunk.core.profiles import config_path, load_profile


def test_load_profile_none_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("VCT_SPLUNK_CONFIG", str(tmp_path / "config"))
    assert load_profile(None) == {}


def test_load_profile_missing_file_is_not_an_error(tmp_path, monkeypatch):
    monkeypatch.setenv("VCT_SPLUNK_CONFIG", str(tmp_path / "absent"))
    assert load_profile("prod") == {}


def test_load_profile_reads_recognized_keys(tmp_path, monkeypatch):
    cfgfile = tmp_path / "config"
    cfgfile.write_text(
        "[prod]\n"
        "url = https://sh:8089\n"
        "session_key = SK\n"
        "app = my_app\n"
        "owner = nobody\n"
        "ignored = nope\n"
    )
    cfgfile.chmod(0o600)
    monkeypatch.setenv("VCT_SPLUNK_CONFIG", str(cfgfile))
    got = load_profile("prod")
    assert got == {
        "url": "https://sh:8089",
        "session_key": "SK",
        "app": "my_app",
        "owner": "nobody",
    }


def test_load_profile_unknown_section_returns_empty(tmp_path, monkeypatch):
    cfgfile = tmp_path / "config"
    cfgfile.write_text("[prod]\nurl = https://sh:8089\n")
    monkeypatch.setenv("VCT_SPLUNK_CONFIG", str(cfgfile))
    assert load_profile("staging") == {}


def test_config_path_prefers_override(tmp_path, monkeypatch):
    monkeypatch.setenv("VCT_SPLUNK_CONFIG", str(tmp_path / "explicit"))
    assert config_path() == tmp_path / "explicit"


def test_config_path_falls_back_to_xdg(tmp_path, monkeypatch):
    monkeypatch.delenv("VCT_SPLUNK_CONFIG", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert config_path() == tmp_path / "vct-splunk" / "config"


def test_profile_credentials_allow_percent_characters(tmp_path, monkeypatch):
    cfgfile = tmp_path / "config"
    cfgfile.write_text("[prod]\ntoken = value%with%percent\n")
    cfgfile.chmod(0o600)
    monkeypatch.setenv("VCT_SPLUNK_CONFIG", str(cfgfile))
    assert load_profile("prod")["token"] == "value%with%percent"


@pytest.mark.skipif(os.name != "posix", reason="POSIX permission bits required")
def test_secret_profile_rejects_group_or_world_access(tmp_path, monkeypatch):
    cfgfile = tmp_path / "config"
    cfgfile.write_text("[prod]\ntoken = secret\n")
    cfgfile.chmod(0o644)
    monkeypatch.setenv("VCT_SPLUNK_CONFIG", str(cfgfile))
    with pytest.raises(UsageError, match="mode 0600"):
        load_profile("prod")
