from __future__ import annotations

import time
import uuid
from pathlib import Path

from . import responses
from .audit import DecisionLog
from .classifier import RequestClassifier, load_classifier
from .conversation import is_follow_up, user_turns
from .emergency import detect_emergency, emergency_response
from .generation import ExtractiveGenerator, Generator
from .normalize import normalize
from .output_check import check_output, render
from .pii import redact
from .policy import GuardrailPolicy
from .retrieval import BM25Retriever, CrossEncoderReranker, Retriever, retrieval_gate
from .types import Action, Decision, GuardedResponse, Intent, Trace

ROOT = Path(__file__).resolve().parents[1]
_STRICTNESS = {Action.ANSWER: 0, Action.NO_SUPPORT: 0, Action.REDIRECT: 1, Action.REFUSE: 2, Action.EMERGENCY: 3}


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

    # Layers 0-3 only: no retrieval or generation. Returns the decision and the
    # (redacted) query to retrieve and answer with.
    def screen(self, question: str, trace: Trace | None = None,
               history: list[dict] | None = None) -> tuple[Decision, str]:
        trace = trace or Trace(uuid.uuid4().hex)
        t0 = time.perf_counter()
        red = redact(question)
        trace.phi_types = list(red.found)
        text = red.text
        conv = self.policy.config.get("conversation", {})
        prior = [redact(t).text for t in user_turns(history)][-conv.get("history_turns", 3):]
        follow_up = bool(prior) and is_follow_up(normalize(text))
        trace.conversation = {"prior_user_turns": len(prior), "follow_up": follow_up, "context_decided": False}

        decision = self._screen_text(text, trace)
        if decision.action is not Action.EMERGENCY and prior:
            decision = self._apply_history(decision, text, prior, follow_up, conv, trace)
        trace.decision = _decision_dict(decision)
        trace.latency_ms["screen"] = _ms(t0)
        # A follow-up ("what about for kids?") is searched together with the question it follows.
        query = f"{prior[-1]} {text}" if follow_up else text
        return decision, query

    def _screen_text(self, text: str, trace: Trace | None = None) -> Decision:
        em = detect_emergency(normalize(text))
        if trace is not None:
            trace.emergency = {"tier": em.tier, "kind": em.kind, "score": em.score}
        if em.tier == "active":
            kind = Intent.SELF_HARM if em.kind == "self_harm" else Intent.EMERGENCY
            return Decision(Action.EMERGENCY, "emergency", kind, em.score, em.reason, (kind.value,))
        c = self.classifier.classify(text)
        if trace is not None:
            trace.classification = c.to_dict()
        return self.policy.decide(c)

    def _apply_history(self, decision: Decision, text: str, prior: list[str], follow_up: bool, conv: dict,
                       trace: Trace) -> Decision:
        # An emergency earlier in the conversation stays in force for the next few turns.
        for turn in prior[len(prior) - conv.get("sticky_emergency_turns", 2):]:
            earlier = self._screen_text(turn)
            if earlier.action is Action.EMERGENCY:
                kind = "self_harm" if earlier.intent is Intent.SELF_HARM else detect_emergency(normalize(turn)).kind
                trace.emergency = {"tier": "active", "kind": kind, "score": earlier.risk, "sticky": True}
                trace.conversation["context_decided"] = True
                return Decision(Action.EMERGENCY, "conversation", earlier.intent, earlier.risk,
                                "emergency earlier in conversation", earlier.kinds)
        # A follow-up is also judged together with the turns before it, and the stricter
        # decision wins, so a risky request cannot be split across messages.
        if follow_up:
            c = self.classifier.classify(" ".join([*prior, text]))
            joined = self.policy.decide(c)
            if _STRICTNESS[joined.action] > _STRICTNESS[decision.action]:
                trace.classification = c.to_dict()
                trace.conversation["context_decided"] = True
                return Decision(joined.action, "conversation", joined.intent, joined.risk,
                                "with conversation context: " + joined.reason)
        return decision

    def ask(self, question: str, history: list[dict] | None = None) -> GuardedResponse:
        """`history` is the conversation so far in chat format
        ([{"role": "user" | "assistant", "content": ...}, ...]), without the new question."""
        trace = Trace(uuid.uuid4().hex)
        decision, query = self.screen(question, trace, history)
        response = self._respond(decision, query, trace)
        response.debug = {**self._debug(decision, trace), **response.debug}
        if self.log:
            self.log.write(trace)
        return response

    def _respond(self, decision: Decision, text: str, trace: Trace) -> GuardedResponse:
        if decision.action is Action.EMERGENCY:
            kinds = list(decision.kinds) or ["self_harm" if decision.intent is Intent.SELF_HARM else "emergency"]
            text_out = emergency_response(kinds, symptom=(trace.emergency or {}).get("kind"))
            return GuardedResponse(Action.EMERGENCY, text_out, [], trace, {"stage": "before LLM"})

        decline = responses.DECLINE.get(decision.intent) if decision.action is not Action.ANSWER else None
        if decision.action is Action.REFUSE:
            return GuardedResponse(Action.REFUSE, decline or responses.NO_SUPPORT, [], trace, {"stage": "before LLM"})

        t0 = time.perf_counter()
        gate = retrieval_gate(self.retriever, text, self.policy.config, redirect=decision.action is Action.REDIRECT,
                              reranker=self.reranker)
        trace.retrieval = gate.to_dict()
        trace.latency_ms["retrieval"] = _ms(t0)
        threshold = self.policy.config["retrieval"]["min_rerank_score_redirect" if decision.action is Action.REDIRECT
                                                    else "min_rerank_score"] if self.reranker else None
        retrieval_debug = {"retrieval": {"passed": gate.passed, "reason": gate.reason, "top_score": round(gate.top_score, 2),
                                         "threshold": threshold,
                                         "top_sources": [f"{p.title} ({p.score:.1f})" for p in gate.passages[:3]]}}
        if not gate.passed:
            response = self._no_support(decision, decline, trace)
            response.debug = {"stage": "before LLM", "blocked_by": "retrieval gate (no strong source)", **retrieval_debug}
            return response

        t0 = time.perf_counter()
        draft = self.generator.generate(text, gate.passages)
        trace.latency_ms["generation"] = _ms(t0)
        check = check_output(draft, gate.passages, self.policy.config, decision.action.value)
        trace.output_check = check.to_dict()
        output_debug = {**retrieval_debug, "llm_draft": draft,
                        "dropped_sentences": [{"reason": r, "sentence": s} for r, s in check.dropped_sentences]}
        if not check.kept:
            response = self._no_support(decision, decline, trace)
            response.debug = {"stage": "after LLM",
                              "blocked_by": "output check (every sentence of the LLM draft was dropped)", **output_debug}
            return response

        body, sources = render(check, gate.passages)
        banner = (trace.emergency or {}).get("tier") == "informational"
        text_out = responses.compose(body, sources, decline=decline, banner=banner)
        partial = f"output check removed {len(check.dropped_sentences)} sentence(s)" if check.dropped_sentences else None
        return GuardedResponse(decision.action, text_out, sources, trace,
                               {"stage": "after LLM", "blocked_by": partial, **output_debug})

    def _debug(self, decision: Decision, trace: Trace) -> dict:
        """What fired and why, in readable form: probabilities as percentages and the
        thresholds they were compared against."""
        by_layer = {"emergency": "emergency fast path (regex match)", "classifier": "classifier (urgent probability)",
                    "policy": "classifier + policy thresholds", "conversation": "conversation context"}
        out = {"action": decision.action.value, "guardrail": by_layer.get(decision.layer, decision.layer),
               "reason": decision.reason}
        if decision.kinds:
            out["emergency_messages"] = list(decision.kinds)
        em = trace.emergency or {}
        if em.get("tier"):
            out["emergency_regex"] = f"{em['tier']} ({em.get('kind')})" + (" [from earlier turn]" if em.get("sticky") else "")
        c = trace.classification
        if c:
            pct = lambda x: f"{100 * x:.0f}%"  # noqa: E731
            out["probabilities"] = {k: pct(v) for k, v in sorted(c["intent_probs"].items(), key=lambda kv: -kv[1])}
            out["personal"], out["injection"] = pct(c["personal"]), pct(c["injection"])
            cfg = self.policy.config
            out["thresholds"] = {"urgent (emergency + self_harm)": pct(cfg["emergency"]["classifier_threshold"]),
                                 "injection": pct(cfg["risk"]["injection_threshold"])}
            if decision.intent and decision.intent.value in cfg["intents"]:
                t = cfg["intents"][decision.intent.value]
                out["thresholds"][f"{decision.intent.value} risk"] = (
                    f"redirect {pct(t['redirect'] + self.policy.shift)}, refuse {pct(min(1.0, t['refuse'] + self.policy.shift))}"
                    f" (risk was {pct(decision.risk)})")
        if trace.conversation and trace.conversation.get("prior_user_turns"):
            out["conversation"] = trace.conversation
        return out

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
