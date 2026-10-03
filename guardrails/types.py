from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum


class Intent(str, Enum):
    INFO = "info"
    DIAGNOSIS = "diagnosis"
    DOSING = "dosing"
    TREATMENT_DECISION = "treatment_decision"
    EMERGENCY = "emergency"
    SELF_HARM = "self_harm"


INTENTS: list[Intent] = list(Intent)
RISKY_INTENTS = (Intent.DIAGNOSIS, Intent.DOSING, Intent.TREATMENT_DECISION)
URGENT_INTENTS = (Intent.EMERGENCY, Intent.SELF_HARM)


class Action(str, Enum):
    ANSWER = "answer"
    # Decline the personal part, still give cited general information on the topic.
    REDIRECT = "redirect"
    REFUSE = "refuse"
    EMERGENCY = "emergency"
    # Retrieval or output grounding could not support an answer.
    NO_SUPPORT = "no_support"


@dataclass(frozen=True)
class Classification:
    """Output of a request classifier (layer 2)."""

    intent_probs: dict[Intent, float]
    personal: float  # P(request is about the user or someone they know)
    injection: float  # P(jailbreak / roleplay / hypothetical framing)
    model: str = ""

    @property
    def top_intent(self) -> Intent:
        return max(self.intent_probs, key=self.intent_probs.get)

    def to_dict(self) -> dict:
        return {
            "intent_probs": {i.value: round(p, 4) for i, p in self.intent_probs.items()},
            "personal": round(self.personal, 4),
            "injection": round(self.injection, 4),
            "model": self.model,
        }


@dataclass(frozen=True)
class Decision:
    """Output of the graded policy (layer 3)."""

    action: Action
    layer: str  # which layer decided: "emergency", "classifier", "policy"
    intent: Intent | None
    risk: float
    reason: str


@dataclass(frozen=True)
class Passage:
    chunk_id: str
    text: str
    title: str
    publisher: str
    source_url: str
    score: float


@dataclass
class Trace:
    """Everything the decision log records. Never holds the question or answer text."""

    request_id: str
    phi_types: list[str] = field(default_factory=list)
    emergency: dict | None = None
    classification: dict | None = None
    decision: dict | None = None
    retrieval: dict | None = None
    output_check: dict | None = None
    latency_ms: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class GuardedResponse:
    action: Action
    text: str
    citations: list[Passage]
    trace: Trace
