"""Apply every Cloud-writable mutation against a real ACS-backed stack, then undo it.

The write-side mirror of `tests/integration/enterprise/write/test_write_catalog.py`,
narrowed to the three resources ACS actually lets this CLI mutate: `index`,
`role`, and `hec-token`. No restart, no app install, no file inputs -- ACS has
no equivalent surface for any of those.

Each test creates one uniquely named object, updates it, deletes it, and polls
the resource's list until the name is gone (ACS index and HEC-token deletes
complete asynchronously, so a `202` response does not mean the object is gone
yet). `cloud_cli.finish()` still fails loudly if the registered reverse
cleanup itself errors -- the poll only proves the delete this test issued
actually completed.
"""

from __future__ import annotations

import time

import pytest

from .conftest import CloudCli, unique_name

pytestmark = [pytest.mark.integration, pytest.mark.cloud, pytest.mark.write]

_POLL_TIMEOUT = 120.0
_POLL_INTERVAL = 3.0


def _poll_until_gone(cloud_cli: CloudCli, resource: str, name: str) -> None:
    """Poll `resource list` until *name* no longer appears, or fail after the timeout."""
    deadline = time.monotonic() + _POLL_TIMEOUT
    while time.monotonic() < deadline:
        items = cloud_cli.run(resource, "list")
        if not any(isinstance(item, dict) and item.get("name") == name for item in items):
            return
        time.sleep(_POLL_INTERVAL)
    pytest.fail(f"{resource} {name!r} is still listed {_POLL_TIMEOUT:.0f}s after delete")


def test_index_create_update_delete(cloud_cli: CloudCli) -> None:
    """Create an index, resize it, delete it, and wait for ACS to finish deleting it."""
    name = unique_name("index")
    label = f"delete index {name}"
    cloud_cli.cleanup(label, "index", "delete", name)

    cloud_cli.write("index", "create", name)
    cloud_cli.write("index", "update", name, "--max-gb", "2")
    cloud_cli.write("index", "delete", name)

    cloud_cli.drop_cleanup(label)  # already deleted above; nothing left to undo
    _poll_until_gone(cloud_cli, "index", name)


def test_role_create_update_delete(cloud_cli: CloudCli) -> None:
    """Create a role, change a setting, delete it, and confirm it is gone."""
    name = unique_name("role")
    label = f"delete role {name}"
    cloud_cli.cleanup(label, "role", "delete", name)

    cloud_cli.write("role", "create", name, "--set", "defaultApp=search")
    cloud_cli.write("role", "update", name, "--set", "srchFilter=search index=main")
    cloud_cli.write("role", "delete", name)

    cloud_cli.drop_cleanup(label)
    _poll_until_gone(cloud_cli, "role", name)


def test_hec_token_create_update_delete(cloud_cli: CloudCli) -> None:
    """Create an HEC token, change a setting, delete it, and confirm it is gone.

    Also proves the ACS create response never shows the minted token -- unlike
    the Enterprise `hec-token create`, which is allowed to reveal it once.
    """
    name = unique_name("hec")
    label = f"delete hec-token {name}"
    cloud_cli.cleanup(label, "hec-token", "delete", name)

    created = cloud_cli.write("hec-token", "create", name, "--set", "defaultIndex=main")
    assert created.get("token") in (None, "<redacted>")

    cloud_cli.write("hec-token", "update", name, "--set", "defaultSourcetype=vct_ci")
    cloud_cli.write("hec-token", "delete", name)

    cloud_cli.drop_cleanup(label)
    _poll_until_gone(cloud_cli, "hec-token", name)
