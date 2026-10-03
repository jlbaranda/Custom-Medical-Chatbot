from __future__ import annotations

import time
import uuid
from pathlib import Path

from . import responses
from .audit import DecisionLog
from .classifier import RequestClassifier, load_classifier
from .emergency import detect_emergency, emergency_response
from .generation import ExtractiveGenerator, Generator
from .normalize import normalize
from .output_check import check_output, render
from .pii import redact
from .policy import GuardrailPolicy
from .retrieval import BM25Retriever, CrossEncoderReranker, Retriever, retrieval_gate
from .types import Action, Decision, GuardedResponse, Intent, Trace

ROOT = Path(__file__).resolve().parents[1]


class GuardedChatbot:
    """Runs every request through the six layers:

    0. PHI redaction       (nothing downstream sees identifiers)
    1. emergency fast path (regex, recall-first)
    2. request classifier  (intent + personal + injection probabilities)
    3. graded policy       (answer / redirect / refuse)
    4. retrieval gate      (no strong source, no answer)
    5. output check        (cited, grounded, no doses or personal claims)
    6. decision log        (why, without the text)
    """

    def __init__(self, classifier: RequestClassifier, retriever: Retriever, generator: Generator,
                 policy: GuardrailPolicy, log: DecisionLog | None = None,
                 reranker: CrossEncoderReranker | None = None):
        self.classifier = classifier
        self.retriever = retriever
        self.generator = generator
        self.policy = policy
        self.log = log
        self.reranker = reranker

    @classmethod
    def from_config(cls, generator: Generator | None = None, retriever: Retriever | None = None,
                    policy: GuardrailPolicy | None = None) -> "GuardedChatbot":
        policy = policy or GuardrailPolicy.from_file()
        cfg = policy.config
        classifier = load_classifier(cfg, ROOT)
        generator = generator or ExtractiveGenerator()
        rcfg = cfg["retrieval"]
        reranker = CrossEncoderReranker(rcfg["reranker"], quantize=rcfg["reranker_quantize"]) if rcfg["reranker"] else None
        versions = {"policy_version": cfg["version"], "policy_hash": cfg["_hash"], "classifier": classifier.name,
                    "reranker": reranker.name if reranker else None, "generator": generator.name}
        log = DecisionLog(ROOT / cfg["log"]["path"], versions, cfg["log"]["enabled"])
        return cls(classifier, retriever or BM25Retriever.from_jsonl(), generator, policy, log, reranker)

    # Layers 0-3 only: no retrieval or generation. Used by the safety eval.
    def screen(self, question: str, trace: Trace | None = None) -> tuple[Decision, str]:
        trace = trace or Trace(uuid.uuid4().hex)
        t0 = time.perf_counter()
        red = redact(question)
        trace.phi_types = list(red.found)
        text = red.text

        em = detect_emergency(normalize(text))
        trace.emergency = {"tier": em.tier, "kind": em.kind, "score": em.score}
        if em.tier == "active":
            kind = Intent.SELF_HARM if em.kind == "self_harm" else Intent.EMERGENCY
            decision = Decision(Action.EMERGENCY, "emergency", kind, em.score, em.reason)
            trace.decision = _decision_dict(decision)
            trace.latency_ms["screen"] = _ms(t0)
            return decision, text

        c = self.classifier.classify(text)
        trace.classification = c.to_dict()
        decision = self.policy.decide(c)
        trace.decision = _decision_dict(decision)
        trace.latency_ms["screen"] = _ms(t0)
        return decision, text

    def ask(self, question: str) -> GuardedResponse:
        trace = Trace(uuid.uuid4().hex)
        decision, text = self.screen(question, trace)
        response = self._respond(decision, text, trace)
        if self.log:
            self.log.write(trace)
        return response

    def _respond(self, decision: Decision, text: str, trace: Trace) -> GuardedResponse:
        if decision.action is Action.EMERGENCY:
            from .emergency import EmergencyResult

            kind = "self_harm" if decision.intent is Intent.SELF_HARM else (trace.emergency or {}).get("kind")
            return GuardedResponse(Action.EMERGENCY, emergency_response(EmergencyResult("active", kind, 1.0)), [], trace)

        decline = responses.DECLINE.get(decision.intent) if decision.action is not Action.ANSWER else None
        if decision.action is Action.REFUSE:
            return GuardedResponse(Action.REFUSE, decline or responses.NO_SUPPORT, [], trace)

        t0 = time.perf_counter()
        gate = retrieval_gate(self.retriever, text, self.policy.config, redirect=decision.action is Action.REDIRECT,
                              reranker=self.reranker)
        trace.retrieval = gate.to_dict()
        trace.latency_ms["retrieval"] = _ms(t0)
        if not gate.passed:
            return self._no_support(decision, decline, trace)

        t0 = time.perf_counter()
        draft = self.generator.generate(text, gate.passages)
        trace.latency_ms["generation"] = _ms(t0)
        check = check_output(draft, gate.passages, self.policy.config, decision.action.value)
        trace.output_check = check.to_dict()
        if not check.kept:
            return self._no_support(decision, decline, trace)

        body, sources = render(check, gate.passages)
        banner = (trace.emergency or {}).get("tier") == "informational"
        text_out = responses.compose(body, sources, decline=decline, banner=banner)
        return GuardedResponse(decision.action, text_out, sources, trace)

    @staticmethod
    def _no_support(decision: Decision, decline: str | None, trace: Trace) -> GuardedResponse:
        if decision.action is Action.REDIRECT and decline:
            # Still decline clearly; just without the general-information part.
            return GuardedResponse(Action.REDIRECT, decline, [], trace)
        return GuardedResponse(Action.NO_SUPPORT, responses.NO_SUPPORT, [], trace)


def _decision_dict(d: Decision) -> dict:
    return {"action": d.action.value, "layer": d.layer, "intent": d.intent.value if d.intent else None,
            "risk": round(d.risk, 4), "reason": d.reason}


def _ms(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000, 2)
