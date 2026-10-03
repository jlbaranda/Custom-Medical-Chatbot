"""Calibrate the retrieval gate threshold on questions labeled answerable / not in corpus.

    python -m guardrails.eval.calibrate_gate

Prints the reranker score per question and the threshold that maximises balanced
accuracy. Labels are approximate (an "unanswerable" topic can be mentioned in passing
in the corpus), so treat the result as a starting point and re-run when the corpus grows.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from ..policy import load_config
from ..retrieval import BM25Retriever, CrossEncoderReranker

DATA = Path(__file__).with_name("gate_calibration.jsonl")


def main() -> None:
    cfg = load_config()["retrieval"]
    rows = [json.loads(line) for line in DATA.read_text(encoding="utf-8").splitlines() if line.strip()]
    retriever = BM25Retriever.from_jsonl()
    reranker = CrossEncoderReranker(cfg["reranker"], quantize=cfg["reranker_quantize"])

    t0 = time.perf_counter()
    scored = []
    for row in rows:
        best = reranker.rerank(row["text"], retriever.search(row["text"], cfg["candidates"]))[0]
        scored.append((best.score, row["answerable"], row["text"], best.title))
    per_q = (time.perf_counter() - t0) / len(rows)

    pos = [s for s, y, *_ in scored if y]
    neg = [s for s, y, *_ in scored if not y]
    best_t, best_bacc = None, -1.0
    for t in sorted({round(s, 1) for s, *_ in scored}):
        tpr = sum(s >= t for s in pos) / len(pos)
        tnr = sum(s < t for s in neg) / len(neg)
        if (tpr + tnr) / 2 > best_bacc:
            best_t, best_bacc = t, (tpr + tnr) / 2

    for s, y, text, title in sorted(scored, reverse=True):
        flag = "" if (s >= best_t) == bool(y) else "  <-- wrong side"
        print(f"{s:6.1f} {'ANS' if y else 'out'} {text[:55]:55s} | {title[:35]}{flag}")
    print(f"\nbest threshold {best_t} balanced acc {best_bacc:.3f} "
          f"(current min_rerank_score {cfg['min_rerank_score']}), {per_q:.2f}s/question")


if __name__ == "__main__":
    main()
