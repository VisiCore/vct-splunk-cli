"""Credential-free drift check against Splunk's public ACS OpenAPI."""

from __future__ import annotations

import os

import httpx
import pytest

from vct_splunk.core.acs.operations import LIST_ENVELOPES

pytestmark = pytest.mark.integration

_SOURCE = "https://admin.splunk.com/service/info/specs/v2/openapi.json"


def test_implemented_acs_contract_matches_public_spec():
    if os.environ.get("SPLUNK_ACS_SPEC_TEST") != "true":
        pytest.skip("set SPLUNK_ACS_SPEC_TEST=true to check the public ACS OpenAPI")

    public = httpx.get(_SOURCE, timeout=30).raise_for_status().json()
    for path, envelope in LIST_ENVELOPES.items():
        operation = public["paths"][f"/{{stack}}/adminconfig/v2/{path}"]["get"]
        assert [parameter["$ref"].rsplit("/", 1)[-1] for parameter in operation["parameters"]] == (
            ["stack", "count", "offset"]
        )
        schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
        assert schema["properties"][envelope]["type"] == "array"
