"""Evidence-balanced retrieval for explicit two-condition comparisons.

This module only activates for questions that explicitly ask to compare TWO
supported topics. Each topic passes the existing retrieval gate independently.
No thresholds are lowered, and generation is blocked if either topic lacks
sufficient cited evidence.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

# Terms reflect the project's ten MedlinePlus topics; aliases are for retrieval
# recognition only, not statements about medical equivalence or diagnoses.
TOPIC_ALIASES = {
    "diabetes": ("diabetes",),
    "asthma": ("asthma",),
    "high blood pressure": ("high blood pressure", "hypertension"),
    "flu": ("influenza", "flu"),
    "migraine": ("migraines", "migraine"),
    "anemia": ("anaemia", "anemia"),
    "hypothyroidism": ("hypothyroidism", "underactive thyroid"),
    "cholesterol": ("high cholesterol", "cholesterol"),
    "allergy": ("allergies", "allergy"),
    "pneumonia": ("pneumonia",),
}

_COMPARISON = re.compile(
    r"\b(?:compare|comparison|contrasts?|versus|vs\.?|differences?|different|differ|distinguish)\b",
    re.I,
)


def detect_comparison(question: str) -> tuple[str, str] | None:
    """Recognize an explicit comparison between exactly two known topics."""
    if not _COMPARISON.search(question):
        return None
    positions: list[tuple[int, str]] = []
    for topic, aliases in TOPIC_ALIASES.items():
        starts = [m.start() for alias in aliases
                  for m in re.finditer(r"\b" + re.escape(alias) + r"\b", question, re.I)]
        if starts:
            positions.append((min(starts), topic))
    if len(positions) != 2:
        return None
    positions.sort()
    return positions[0][1], positions[1][1]


def _topic_question(topic: str, original_question: str) -> str:
    """Search the same aspect of each topic when a comparison names one."""
    if re.search(r"\b(?:symptoms?|signs?)\b", original_question, re.I):
        return f"What are the symptoms of {topic}?"
    if re.search(r"\b(?:diagnos(?:e|is|ed|ing|tic)|tests?|testing)\b", original_question, re.I):
        return f"How is {topic} diagnosed?"
    if re.search(r"\b(?:causes?|triggers?)\b", original_question, re.I):
        return f"What causes {topic}?"
    if re.search(r"\b(?:treatments?|treat(?:ed|ing)?|therap(?:y|ies))\b", original_question, re.I):
        return f"What are the treatments for {topic}?"
    return f"What is {topic}?"


def _title_mentions_topic(title: str, topic: str) -> bool:
    return any(re.search(r"\b" + re.escape(alias) + r"\b", title, re.I)
               for alias in TOPIC_ALIASES[topic])


@dataclass
class ComparisonGateResult:
    passed: bool
    passages: list[Any]
    top_score: float
    coverage: float
    reason: str
    topics: tuple[str, str]
    topic_scores: dict[str, float]
    topic_source_count: dict[str, int]

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "top_score": round(self.top_score, 3) if math.isfinite(self.top_score) else None,
            "coverage": self.coverage,
            "n_passages": len(self.passages),
            "chunk_ids": [p.chunk_id for p in self.passages],
            "reason": self.reason,
            "comparison_topics": list(self.topics),
            "topic_scores": {k: (round(v, 3) if math.isfinite(v) else None)
                              for k, v in self.topic_scores.items()},
            "topic_source_count": self.topic_source_count,
        }


def comparison_retrieval_gate(retriever, original_question: str,
                              config: dict, topics: tuple[str, str],
                              *, redirect: bool, reranker) -> ComparisonGateResult:
    """Get at least one relevant source for EACH topic or fail closed.

    Calls the existing threshold-aware gate for each subquestion. Then selects
    at most two distinct sources from each side (or fewer if top_k < 4).
    This never weakens emergency, intent, reranker, or output safeguards.
    """
    from .retrieval import retrieval_gate  # Deferred to prevent circular import.

    cfg = config["retrieval"]
    slots = max(1, cfg["top_k"] // 2)
    selected = []
    seen = set()
    scores: dict[str, float] = {}
    counts: dict[str, int] = {}
    failures = []

    for topic in topics:
        # The original question is kept for generation. The simple subquestion
        # is only used to retrieve independently relevant evidence.
        question = _topic_question(topic, original_question)
        gate = retrieval_gate(retriever, question, config, redirect=redirect, reranker=reranker)
        scores[topic] = gate.top_score
        topic_passages = []
        for passage in gate.passages:
            source_id = passage.source_url or passage.chunk_id
            if source_id in seen or not _title_mentions_topic(passage.title, topic):
                continue
            seen.add(source_id)
            topic_passages.append(passage)
            if len(topic_passages) >= slots:
                break
        counts[topic] = len(topic_passages)
        if not gate.passed:
            failures.append(f"{topic}: {gate.reason}")
        elif not topic_passages:
            failures.append(f"{topic}: no topic-specific cited source passed the gate")
        selected.extend(topic_passages)

    passed = not failures
    # The weakest of the two independent relevance scores determines support.
    weakest_score = min(scores.values()) if scores else float("-inf")
    return ComparisonGateResult(
        passed=passed,
        passages=selected if passed else [],
        top_score=weakest_score,
        coverage=1.0 if passed else 0.0,
        reason="comparison: evidence for both topics" if passed else "comparison blocked: " + "; ".join(failures),
        topics=topics,
        topic_scores=scores,
        topic_source_count=counts,
    )
