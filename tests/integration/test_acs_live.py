"""Credential-gated read-only ACS canary."""

from __future__ import annotations

import os

import pytest

from vct_splunk.core.acs import operations
from vct_splunk.core.acs.client import AcsClient, acs_config_from_env
from vct_splunk.core.backends import cloud_stack_from_url

pytestmark = [
    pytest.mark.integration,
    pytest.mark.cloud,
    pytest.mark.acs,
    pytest.mark.read,
]


@pytest.fixture
def acs_client():
    if os.environ.get("SPLUNK_ACS_LIVE_TEST") != "true":
        pytest.skip("set SPLUNK_ACS_LIVE_TEST=true with ACS credentials")
    with AcsClient(acs_config_from_env(cloud_stack_from_url())) as client:
        yield client


def test_live_acs_index_list(acs_client):
    assert isinstance(operations.list_cloud_indexes(acs_client), list)


def test_live_acs_role_list(acs_client):
    assert isinstance(operations.list_cloud_roles(acs_client), list)


def test_live_acs_hec_list_has_no_tokens(acs_client):
    result = operations.list_hec_tokens(acs_client)
    assert isinstance(result, list)
    assert all("token" not in item for item in result)
