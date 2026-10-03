from __future__ import annotations

import json
import time
from pathlib import Path

from .types import Trace

# Layer 6: decision log. One JSON line per request with which layer fired and why.
# The question and answer text are never written: only PHI *types* found,
# probabilities, thresholds crossed, chunk ids, and versions.


class DecisionLog:
    def __init__(self, path: Path, versions: dict, enabled: bool = True):
        self.path = path
        self.versions = versions
        self.enabled = enabled

    def write(self, trace: Trace) -> None:
        if not self.enabled:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        entry = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **self.versions, **trace.to_dict()}
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
