from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .normalize import content_tokens, normalize
from .types import Passage

# Layer 4: retrieval gate. The team's real retriever (MedCPT / BiomedBERT embeddings)
# plugs in through the Retriever protocol; BM25 is the dependency-light default and
# a lexical baseline to compare against.

CHUNKS_PATH = Path(__file__).resolve().parents[1] / "data" / "chunks" / "chunks.jsonl"


class Retriever(Protocol):
    def search(self, query: str, k: int) -> list[Passage]: ...


class BM25Retriever:
    def __init__(self, chunks: list[dict]):
        from rank_bm25 import BM25Okapi

        self.chunks = chunks
        self.bm25 = BM25Okapi([content_tokens(c["text"]) for c in chunks])

    @classmethod
    def from_jsonl(cls, path: Path = CHUNKS_PATH) -> "BM25Retriever":
        with open(path, encoding="utf-8") as fh:
            return cls([json.loads(line) for line in fh if line.strip()])

    def search(self, query: str, k: int) -> list[Passage]:
        scores = self.bm25.get_scores(content_tokens(normalize(query)))
        top = sorted(range(len(scores)), key=scores.__getitem__, reverse=True)[:k]
        return [
            Passage(c["chunk_id"], c["text"], c.get("title", ""), c.get("publisher", ""), c.get("source_url", ""),
                    float(scores[i]))
            for i in top
            for c in [self.chunks[i]]
        ]


class CrossEncoderReranker:
    """Scores (query, passage) relevance jointly. Its score is what the gate trusts:
    unlike raw BM25 it is comparable across queries, so one threshold works."""

    def __init__(self, model_name: str, max_length: int = 256, quantize: bool = False):
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self._torch = torch
        self.name = model_name
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_name).eval()
        if quantize:
            # int8 dynamic quantization: ~2x faster on CPU but shifts scores; recalibrate thresholds if enabled.
            self.model = torch.quantization.quantize_dynamic(self.model, {torch.nn.Linear}, dtype=torch.qint8)
        self.max_length = max_length

    def rerank(self, query: str, passages: list[Passage]) -> list[Passage]:
        if not passages:
            return []
        with self._torch.inference_mode():
            enc = self.tokenizer([query] * len(passages), [p.text for p in passages], truncation=True,
                                 max_length=self.max_length, padding=True, return_tensors="pt")
            scores = self.model(**enc).logits.squeeze(-1).tolist()
        rescored = [Passage(p.chunk_id, p.text, p.title, p.publisher, p.source_url, float(s))
                    for p, s in zip(passages, scores)]
        return sorted(rescored, key=lambda p: p.score, reverse=True)


@dataclass(frozen=True)
class GateResult:
    passed: bool
    passages: list[Passage]
    top_score: float
    coverage: float
    reason: str

    def to_dict(self) -> dict:
        return {"passed": self.passed, "top_score": round(self.top_score, 3), "coverage": round(self.coverage, 3),
                "n_passages": len(self.passages), "chunk_ids": [p.chunk_id for p in self.passages], "reason": self.reason}


def retrieval_gate(retriever: Retriever, query: str, config: dict, redirect: bool = False,
                   reranker: CrossEncoderReranker | None = None) -> GateResult:
    cfg = config["retrieval"]
    if reranker is not None:
        passages = reranker.rerank(query, retriever.search(query, cfg["candidates"]))[: cfg["top_k"]]
        top = passages[0].score if passages else float("-inf")
        threshold = cfg["min_rerank_score_redirect"] if redirect else cfg["min_rerank_score"]
        if top < threshold:
            return GateResult(False, passages, top, 0.0, f"rerank score {top:.1f} < {threshold}")
        kept = [p for p in passages if p.score >= threshold - cfg["rerank_keep_margin"]]
        return GateResult(True, kept, top, 1.0, "ok")

    # Lexical fallback when no reranker is configured.
    min_coverage = cfg["min_coverage_redirect"] if redirect else cfg["min_coverage"]
    passages = retriever.search(query, cfg["top_k"])
    q_terms = set(content_tokens(normalize(query)))
    found = set()
    for p in passages:
        found |= q_terms & set(content_tokens(p.text))
    coverage = len(found) / len(q_terms) if q_terms else 0.0
    top = passages[0].score if passages else 0.0
    if top < cfg["min_score"]:
        return GateResult(False, passages, top, coverage, f"top score {top:.1f} < {cfg['min_score']}")
    if coverage < min_coverage:
        return GateResult(False, passages, top, coverage, f"coverage {coverage:.2f} < {min_coverage}")
    # Keep only passages reasonably close to the best one.
    kept = [p for p in passages if p.score >= 0.5 * top]
    return GateResult(True, kept, top, coverage, "ok")
