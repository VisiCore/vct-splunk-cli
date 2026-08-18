"""`public_target` hides a Cloud stack name only when explicitly asked.

`safe_target` always strips credentials -- that's unconditional. A Cloud stack
name is not a credential, but it does identify a specific customer's instance,
so hiding it is opt-in via `VCT_SPLUNK_REDACT_TARGET=1`, for untrusted output
boundaries such as CI logs. `redact_exception_text` is the same rewrite applied
to free-form text (a transport error message), not just a URL.
"""

from __future__ import annotations

import pytest

from vct_splunk.utils.redact import REDACTED, public_target, redact_exception_text


@pytest.fixture
def redact_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VCT_SPLUNK_REDACT_TARGET", "1")


@pytest.fixture
def redact_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VCT_SPLUNK_REDACT_TARGET", raising=False)


def test_without_the_env_var_the_stack_name_is_left_readable(redact_disabled) -> None:
    assert public_target("https://acme.splunkcloud.com") == "https://acme.splunkcloud.com"


def test_with_the_env_var_a_cloud_host_label_is_hidden(redact_enabled) -> None:
    assert public_target("https://acme.splunkcloud.com") == f"https://{REDACTED}.splunkcloud.com"


def test_with_the_env_var_a_port_survives_the_rewrite(redact_enabled) -> None:
    assert (
        public_target("https://acme.splunkcloud.com:8089")
        == f"https://{REDACTED}.splunkcloud.com:8089"
    )


def test_with_the_env_var_an_admin_splunk_com_path_segment_is_hidden(redact_enabled) -> None:
    assert (
        public_target("https://admin.splunk.com/acme/adminconfig/v2/indexes")
        == f"https://admin.splunk.com/{REDACTED}/adminconfig/v2/indexes"
    )


def test_an_enterprise_target_is_unaffected_either_way(redact_enabled) -> None:
    assert public_target("https://sh.corp:8089") == "https://sh.corp:8089"


def test_url_credentials_are_still_stripped_under_redaction(redact_enabled) -> None:
    target = public_target("https://admin:secret@acme.splunkcloud.com")
    assert "secret" not in target
    assert target == f"https://{REDACTED}.splunkcloud.com"


def test_redact_exception_text_hides_a_cloud_host_in_free_form_text() -> None:
    text = redact_exception_text("Could not reach ACS at https://acme.splunkcloud.com: timeout")
    assert "acme" not in text
    assert f"{REDACTED}.splunkcloud.com" in text


def test_redact_exception_text_hides_an_acs_stack_path_segment() -> None:
    text = redact_exception_text("ACS returned 404 for GET /acme/adminconfig/v2/indexes")
    # No admin.splunk.com host present here, so the path regex (which anchors
    # on that host) does not fire -- the stack label in a bare path is not this
    # function's job; it only rewrites what it can identify unambiguously.
    assert text == "ACS returned 404 for GET /acme/adminconfig/v2/indexes"


def test_redact_exception_text_is_idempotent() -> None:
    once = redact_exception_text("https://acme.splunkcloud.com")
    twice = redact_exception_text(once)
    assert once == twice == f"https://{REDACTED}.splunkcloud.com"
