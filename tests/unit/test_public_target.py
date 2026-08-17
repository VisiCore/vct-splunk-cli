"""Tests for Cloud stack redaction at user-visible output boundaries."""

from __future__ import annotations

from vct_splunk.utils.redact import (
    REDACT_TARGET_ENV,
    public_target,
    redact_exception_text,
    safe_target,
)


def test_safe_target_keeps_cloud_hostname_when_public_redaction_is_disabled(monkeypatch):
    monkeypatch.delenv(REDACT_TARGET_ENV, raising=False)

    assert safe_target("https://acme.splunkcloud.com:8089") == "https://acme.splunkcloud.com:8089"


def test_public_target_hides_cloud_stack_when_enabled(monkeypatch):
    monkeypatch.setenv(REDACT_TARGET_ENV, "1")

    target = public_target("https://acme.splunkcloud.com:8089/services")

    assert "acme" not in target
    assert target == "https://<redacted>.splunkcloud.com:8089/services"


def test_redact_exception_text_hides_acs_and_cloud_stack_labels():
    text = (
        "https://admin.splunk.com/acme/adminconfig/v2/indexes and https://acme.splunkcloud.com/foo"
    )

    redacted = redact_exception_text(text)

    assert "acme" not in redacted
    assert "https://admin.splunk.com/<redacted>/adminconfig/v2/indexes" in redacted
    assert "https://<redacted>.splunkcloud.com/foo" in redacted
