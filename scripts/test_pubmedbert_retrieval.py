import sys
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1]),
)

from retrieval.pubmedbert import PubMedBERTRetriever


def main():
    retriever = PubMedBERTRetriever()

    results = retriever.search(
        "What are symptoms of hypothyroidism?",
        k=5,
    )

    for i, result in enumerate(results, start=1):
        print("=" * 80)
        print(f"Result {i}")
        print(f"Score: {result.score:.4f}")
        print(f"Title: {result.title}")
        print(f"Publisher: {result.publisher}")
        print(f"Source: {result.source_url}")
        print()
        print(result.text[:500])
        print()


if __name__ == "__main__":
    main()