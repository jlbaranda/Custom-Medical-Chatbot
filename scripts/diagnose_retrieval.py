"""Inspect an unanswered comparison and each topic separately (no Qwen needed).

Usage:
    python scripts/diagnose_retrieval.py
    python scripts/diagnose_retrieval.py --topic-a asthma --topic-b pneumonia

This is a diagnostic only. Do NOT lower retrieval thresholds based on one case.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from guardrails.policy import GuardrailPolicy
from guardrails.retrieval import CrossEncoderReranker
from retrieval.pubmedbert import PubMedBERTRetriever


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--topic-a", default="asthma")
    ap.add_argument("--topic-b", default="pneumonia")
    args = ap.parse_args()

    cfg = GuardrailPolicy.from_file().config["retrieval"]
    retriever = PubMedBERTRetriever()
    reranker = CrossEncoderReranker(
        cfg["reranker"], quantize=cfg["reranker_quantize"]
    )
    questions = [
        f"What are the differences between {args.topic_a} and {args.topic_b}?",
        f"What is {args.topic_a}?",
        f"What is {args.topic_b}?",
        f"How is {args.topic_a} diagnosed?",
    ]
    print(f"Current threshold: {cfg['min_rerank_score']}")
    print("These scores are relevance signals, not probabilities or proof of correctness.\n")
    for question in questions:
        candidates = retriever.search(question, cfg["candidates"])
        ranked = reranker.rerank(question, candidates)
        top_score = ranked[0].score if ranked else float("-inf")
        print(f"\nQUESTION: {question}")
        print(f"RETRIEVAL GATE: {'PASS' if top_score >= cfg['min_rerank_score'] else 'BLOCK'}")
        for passage in ranked[:cfg["top_k"]]:
            print(f"  score={passage.score:6.2f} | {passage.title} | {passage.chunk_id}")
            print(f"    {passage.source_url}")
    print("\nNext: manually inspect which chunks cover EACH topic in the comparison.")


if __name__ == "__main__":
    main()
