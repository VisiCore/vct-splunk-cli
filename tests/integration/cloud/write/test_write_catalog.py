"""Apply every Cloud-writable mutation against a real ACS-backed stack, then undo it.

The write-side mirror of `tests/integration/enterprise/write/test_write_catalog.py`,
narrowed to the three resources ACS actually lets this CLI mutate: `index`,
`role`, and `hec-token`. No restart, no app install, no file inputs -- ACS has
no equivalent surface for any of those. All three follow the same shape
(create, change one setting, delete, poll until gone), so they run as one
parametrized test rather than three near-identical copies.

Each case creates one uniquely named object, updates it, deletes it, and polls
the resource's list until the name is gone (ACS index and HEC-token deletes
complete asynchronously, so a `202` response does not mean the object is gone
yet). `cloud_cli.finish()` still fails loudly if the registered reverse
cleanup itself errors -- the poll only proves the delete this test issued
actually completed.
"""

from __future__ import annotations

import time

import pytest

from write_test_cli import WriteTestCli

from .conftest import unique_name

pytestmark = [pytest.mark.integration, pytest.mark.cloud, pytest.mark.write]

_POLL_TIMEOUT = 120.0
_POLL_INTERVAL = 3.0

#: resource -> (create args beyond the name, update args). Each case creates
#: with the given extra args, updates with the given args, deletes, and polls
#: until the name is gone from `<resource> list`.
_CASES: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    ("index", (), ("--max-gb", "2")),
    ("role", ("--set", "defaultApp=search"), ("--set", "srchFilter=search index=main")),
    ("hec-token", ("--set", "defaultIndex=main"), ("--set", "defaultSourcetype=vct_ci")),
)


def _poll_until_gone(cloud_cli: WriteTestCli, resource: str, name: str) -> None:
    """Poll `resource list` until *name* no longer appears, or fail after the timeout."""
    deadline = time.monotonic() + _POLL_TIMEOUT
    while time.monotonic() < deadline:
        items = cloud_cli.run(resource, "list")
        if not any(isinstance(item, dict) and item.get("name") == name for item in items):
            return
        time.sleep(_POLL_INTERVAL)
    pytest.fail(f"{resource} {name!r} is still listed {_POLL_TIMEOUT:.0f}s after delete")


@pytest.mark.parametrize("resource, create_args, update_args", _CASES, ids=lambda v: v)
def test_create_update_delete(
    cloud_cli: WriteTestCli,
    resource: str,
    create_args: tuple[str, ...],
    update_args: tuple[str, ...],
) -> None:
    """Create one object, change a setting, delete it, and confirm ACS finished deleting it.

    The hec-token case also proves the ACS create response never shows the
    minted token -- unlike the Enterprise `hec-token create`, which is allowed
    to reveal it once.
    """
    name = unique_name(resource.replace("-", "_"))
    label = f"delete {resource} {name}"
    cloud_cli.cleanup(label, resource, "delete", name)

    created = cloud_cli.write(resource, "create", name, *create_args)
    if resource == "hec-token":
        assert created.get("token") in (None, "<redacted>")

    cloud_cli.write(resource, "update", name, *update_args)
    cloud_cli.write(resource, "delete", name)

    cloud_cli.drop_cleanup(label)  # already deleted above; nothing left to undo
    _poll_until_gone(cloud_cli, resource, name)
