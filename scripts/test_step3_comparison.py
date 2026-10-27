"""Run comparison retrieval without paying for slow local LLM generation.

    python scripts/test_step3_comparison.py
    python scripts/test_step3_comparison.py --question "Compare diabetes and hypothyroidism"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from guardrails.comparison import detect_comparison
from guardrails.policy import GuardrailPolicy
from guardrails.retrieval import CrossEncoderReranker, retrieval_gate
from retrieval.pubmedbert import PubMedBERTRetriever


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--question', default='What are the differences between asthma and pneumonia?')
    args = p.parse_args()
    cfg = GuardrailPolicy.from_file().config
    topics = detect_comparison(args.question)
    if not topics:
        raise SystemExit('Not an explicit comparison of two supported medical topics.')
    print('Comparison topics:', ' / '.join(topics))
    print('Retrieving separately for both conditions (no LLM generation).')
    rcfg = cfg['retrieval']
    retriever = PubMedBERTRetriever()
    reranker = (CrossEncoderReranker(rcfg['reranker'], quantize=rcfg['reranker_quantize'])
                if rcfg['reranker'] else None)
    result = retrieval_gate(retriever, args.question, cfg, reranker=reranker)
    print('Passed:', result.passed)
    print('Reason:', result.reason)
    print('Topic scores:', getattr(result, 'topic_scores', {}))
    print('Topic source counts:', getattr(result, 'topic_source_count', {}))
    for index, passage in enumerate(result.passages, start=1):
        print(f'[{index}] {passage.title} | score={passage.score:.2f}')
        print(f'    {passage.source_url}')
    if not result.passed:
        print('The chatbot will refuse this comparison unless both topics pass the normal gate.')


if __name__ == '__main__':
    main()
