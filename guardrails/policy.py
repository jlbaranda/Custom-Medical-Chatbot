from __future__ import annotations

import hashlib
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .types import RISKY_INTENTS, URGENT_INTENTS, Action, Classification, Decision, Intent

POLICY_PATH = Path(__file__).with_name("policy.toml")


def load_config(path: Path = POLICY_PATH) -> dict:
    raw = path.read_bytes()
    config = tomllib.loads(raw.decode("utf-8"))
    config["_hash"] = hashlib.sha256(raw).hexdigest()[:12]
    return config


@dataclass
class GuardrailPolicy:
    """Layer 3: turns classifier probabilities into a graded action.

    `threshold_shift` moves every redirect/refuse threshold at once. Negative values
    refuse more (stricter), positive values refuse less. Left as None it uses the
    deployed value from policy.toml; an explicit value replaces it (absolute, not
    added), so sweeps and the deployed setting are always on the same scale.
    """

    config: dict
    threshold_shift: float | None = None

    @classmethod
    def from_file(cls, path: Path = POLICY_PATH, threshold_shift: float | None = None) -> "GuardrailPolicy":
        return cls(load_config(path), threshold_shift)

    @property
    def shift(self) -> float:
        if self.threshold_shift is not None:
            return self.threshold_shift
        return self.config["risk"].get("threshold_shift", 0.0)

    def risk(self, c: Classification, intent: Intent) -> float:
        w = self.config["risk"]["general_weight"]
        return c.intent_probs[intent] * (w + (1 - w) * c.personal)

    def decide(self, c: Classification) -> Decision:
        urgent = sum(c.intent_probs[i] for i in URGENT_INTENTS)
        if urgent >= self.config["emergency"]["classifier_threshold"]:
            top = max(URGENT_INTENTS, key=lambda i: c.intent_probs[i])
            return Decision(Action.EMERGENCY, "classifier", top, urgent, f"P(urgent)={urgent:.2f}")

        # Pick the risky intent whose risk is furthest past its own redirect threshold.
        best: tuple[float, Intent, float] | None = None
        for intent in RISKY_INTENTS:
            r = self.risk(c, intent)
            margin = r - self._threshold(intent, "redirect")
            if best is None or margin > best[0]:
                best = (margin, intent, r)
        margin, intent, r = best

        if margin < 0:
            return Decision(Action.ANSWER, "policy", Intent.INFO, r, f"max risk {intent.value}={r:.2f} below redirect")
        injected = c.injection >= self.config["risk"]["injection_threshold"]
        if r >= self._threshold(intent, "refuse") or injected:
            why = "injection framing" if injected and r < self._threshold(intent, "refuse") else "above refuse"
            return Decision(Action.REFUSE, "policy", intent, r, f"{intent.value} risk={r:.2f} {why}")
        return Decision(Action.REDIRECT, "policy", intent, r, f"{intent.value} risk={r:.2f} redirect band")

    def _threshold(self, intent: Intent, kind: str) -> float:
        shift = self.shift
        return min(1.0, max(0.0, self.config["intents"][intent.value][kind] + shift))
