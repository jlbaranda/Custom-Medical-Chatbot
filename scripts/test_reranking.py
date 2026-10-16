import sys
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1]),
)

from guardrails.policy import GuardrailPolicy
from guardrails.retrieval import CrossEncoderReranker, retrieval_gate
from retrieval.pubmedbert import PubMedBERTRetriever


QUESTION = "What are symptoms of hypothyroidism?"


def print_passages(title, passages):
    print()
    print("=" * 100)
    print(title)
    print("=" * 100)

    for i, passage in enumerate(passages, start=1):
        print()
        print(f"Result {i}")
        print(f"Score: {passage.score:.4f}")
        print(f"Title: {passage.title}")
        print(f"Publisher: {passage.publisher}")
        print(f"Source: {passage.source_url}")
        print()
        print(passage.text[:500])
        print("-" * 100)


def main():
    # Load the existing guardrail configuration.
    policy = GuardrailPolicy.from_file()
    retrieval_config = policy.config["retrieval"]

    # Your new semantic retriever.
    retriever = PubMedBERTRetriever()

    candidate_count = retrieval_config["candidates"]

    # ---------------------------------------------------------
    # Stage 1: PubMedBERT semantic retrieval
    # ---------------------------------------------------------

    candidates = retriever.search(
        QUESTION,
        k=candidate_count,
    )

    print_passages(
        "BEFORE RERANKING - PubMedBERT",
        candidates,
    )

    # ---------------------------------------------------------
    # Stage 2: MedCPT cross-encoder reranking
    # ---------------------------------------------------------

    reranker = CrossEncoderReranker(
        model_name=retrieval_config["reranker"],
        quantize=retrieval_config["reranker_quantize"],
    )

    reranked = reranker.rerank(
        QUESTION,
        candidates,
    )

    print_passages(
        "AFTER RERANKING - MedCPT",
        reranked,
    )

    # ---------------------------------------------------------
    # Stage 3: Run the actual repo retrieval gate
    # ---------------------------------------------------------

    gate = retrieval_gate(
        retriever=retriever,
        query=QUESTION,
        config=policy.config,
        reranker=reranker,
    )

    print()
    print("=" * 100)
    print("RETRIEVAL GATE")
    print("=" * 100)

    print(f"Passed: {gate.passed}")
    print(f"Top score: {gate.top_score:.4f}")
    print(f"Reason: {gate.reason}")
    print(f"Passages kept: {len(gate.passages)}")

    print_passages(
        "PASSAGES THAT WOULD BE SENT TO QWEN",
        gate.passages,
    )


if __name__ == "__main__":
    main()