import sys
import argparse
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1]),
)

from guardrails import GuardedChatbot
from guardrails.generation import OllamaGenerator
from retrieval.pubmedbert import PubMedBERTRetriever


LANGUAGE_MODEL = (
    "huggingface.co/unsloth/Qwen3.5-4B-GGUF:latest"
)


def main():
    retriever = PubMedBERTRetriever()

    generator = OllamaGenerator(
        model=LANGUAGE_MODEL,
        timeout=600,
    )

    bot = GuardedChatbot.from_config(
        retriever=retriever,
        generator=generator,
    )

    parser = argparse.ArgumentParser()
    parser.add_argument(
    "--question",
    default="What are symptoms of hypothyroidism?",
        )
    args = parser.parse_args()

    question = args.question

    response = bot.ask(question)

    print("=" * 100)
    print("QUESTION")
    print("=" * 100)
    print(question)

    print()
    print("=" * 100)
    print("ACTION")
    print("=" * 100)
    print(response.action.value)

    print()
    print("=" * 100)
    print("ANSWER")
    print("=" * 100)
    print(response.text)

    print()
    print("=" * 100)
    print("RETRIEVAL TRACE")
    print("=" * 100)
    print(response.trace.retrieval)

    print()
    print("=" * 100)
    print("OUTPUT CHECK")
    print("=" * 100)
    print(response.trace.output_check)
    print()
    print("=" * 100)
    print("LATENCY")
    print("=" * 100)
    print(response.trace.latency_ms)

if __name__ == "__main__":
    main()