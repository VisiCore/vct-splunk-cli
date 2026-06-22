"""Append-only local audit log for writes. Click-free core.

Location: $VCT_SPLUNK_AUDIT, else $XDG_STATE_HOME/vct-splunk/audit.log,
else ~/.local/state/vct-splunk/audit.log.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


def _audit_path() -> Path:
    override = os.environ.get("VCT_SPLUNK_AUDIT")
    if override:
        return Path(override)
    state = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(state) / "vct-splunk" / "audit.log"


def record(event: dict[str, Any]) -> str:
    path = _audit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps({"ts": int(time.time()), **event}, sort_keys=True, default=str)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    return str(path)
