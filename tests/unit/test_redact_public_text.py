"""`redact_public_text` hides a Cloud stack name only when explicitly asked.

`safe_target` always strips credentials -- that's unconditional. A Cloud stack
name is not a credential, but it does identify a specific customer's instance,
so hiding it is opt-in via `VCT_SPLUNK_REDACT_TARGET`, for untrusted output
boundaries such as CI logs. The output formatter applies it to everything it
renders.
"""

from __future__ import annotations

import pytest

from vct_splunk.utils.redact import REDACTED, redact_public_text, safe_target


@pytest.fixture
def redact_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VCT_SPLUNK_REDACT_TARGET", "1")


def test_without_the_env_var_the_stack_name_is_left_readable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("VCT_SPLUNK_REDACT_TARGET", raising=False)
    assert redact_public_text("https://acme.splunkcloud.com") == "https://acme.splunkcloud.com"


@pytest.mark.parametrize("value", ["1", "TRUE", " yes "])
def test_truthy_env_values_hide_a_cloud_host_label(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("VCT_SPLUNK_REDACT_TARGET", value)
    assert (
        redact_public_text("https://acme.splunkcloud.com") == f"https://{REDACTED}.splunkcloud.com"
    )


def test_a_port_survives_the_rewrite(redact_enabled) -> None:
    assert (
        redact_public_text("https://acme.splunkcloud.com:8089")
        == f"https://{REDACTED}.splunkcloud.com:8089"
    )


def test_an_enterprise_target_is_unaffected(redact_enabled) -> None:
    assert redact_public_text("https://sh.corp:8089") == "https://sh.corp:8089"


def test_url_credentials_are_still_stripped_under_redaction(redact_enabled) -> None:
    target = redact_public_text(safe_target("https://admin:secret@acme.splunkcloud.com"))
    assert target == f"https://{REDACTED}.splunkcloud.com"


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        (
            "ACS request failed: https://admin.splunk.com/acme/adminconfig/v2/indexes",
            "https://admin.splunk.com/<redacted>/adminconfig/v2/indexes",
        ),
        (
            "ACS request failed: https://admin.splunkcloudgc.com/acme/adminconfig/v2/indexes",
            "https://admin.splunkcloudgc.com/<redacted>/adminconfig/v2/indexes",
        ),
        (
            "ACS returned 404 for GET /acme/adminconfig/v2/indexes",
            "GET /<redacted>/adminconfig/v2/indexes",
        ),
    ],
)
def test_an_acs_stack_path_segment_is_hidden(redact_enabled, message: str, expected: str) -> None:
    text = redact_public_text(message)
    assert expected in text
    assert "acme" not in text


def test_redaction_is_idempotent(redact_enabled) -> None:
    once = redact_public_text("https://acme.splunkcloud.com")
    assert redact_public_text(once) == once == f"https://{REDACTED}.splunkcloud.com"
