from __future__ import annotations

import pytest

from vct_splunk.core.errors import UsageError
from vct_splunk.core.namespace import ns_path, resolve_ns


def test_ns_path_builds_servicesns():
    assert (
        ns_path("saved/searches", owner="nobody", app="my_app")
        == "/servicesNS/nobody/my_app/saved/searches"
    )
    assert ns_path("/saved/searches/x", owner="-", app="-") == "/servicesNS/-/-/saved/searches/x"


def test_ns_path_requires_owner_and_app():
    with pytest.raises(UsageError):
        ns_path("saved/searches", owner="", app="my_app")


def test_resolve_ns_read_defaults_to_wildcard():
    assert resolve_ns(None, None, for_write=False) == ("-", "-")
    assert resolve_ns("alice", None, for_write=False) == ("alice", "-")


def test_resolve_ns_write_requires_app():
    # A write with no app must refuse rather than fall back to the 'search' app.
    with pytest.raises(UsageError):
        resolve_ns(None, None, for_write=True)


def test_resolve_ns_write_defaults_owner_to_nobody():
    assert resolve_ns(None, "my_app", for_write=True) == ("nobody", "my_app")
    assert resolve_ns("alice", "my_app", for_write=True) == ("alice", "my_app")
