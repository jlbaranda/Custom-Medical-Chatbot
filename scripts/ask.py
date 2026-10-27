"""Ask the guarded RAG medical chatbot from the command line.

    python scripts/ask.py "What are the symptoms of asthma?"
    python scripts/ask.py --chat
    python scripts/ask.py --chat --trace
    python scripts/ask.py --debug "What causes anemia?"
    python scripts/ask.py --baseline --chat  # older BM25/extractive baseline

RAG is the default: PubMedBERT retrieval, MedCPT reranking from policy.toml,
and Qwen via Ollama. All answers still pass through GuardedChatbot.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from guardrails import GuardedChatbot  # noqa: E402


DEFAULT_LANGUAGE_MODEL = "huggingface.co/unsloth/Qwen3.5-4B-GGUF:latest"


def build_chatbot(*, baseline: bool = False, model: str = DEFAULT_LANGUAGE_MODEL,
                  timeout: float = 600.0) -> GuardedChatbot:
    """Build the guarded application once, then reuse it for every chat turn.

    The generator is supplied through the existing Generator interface, so a
    cloud generator can replace Ollama later without changing the guardrails.
    """
    if baseline:
        return GuardedChatbot.from_config()

    # Import these only in RAG mode so the baseline remains independently usable.
    from guardrails.generation import OllamaGenerator
    from retrieval.pubmedbert import PubMedBERTRetriever

    try:
        retriever = PubMedBERTRetriever()
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            "PubMedBERT index not found in data/index/pubmedbert/. "
            "If you haven't built it, first run python scripts/run_ingestion.py "
            "and then python scripts/build_rag_index.py."
        ) from exc

    generator = OllamaGenerator(model=model, timeout=timeout)
    # from_config loads the existing classifier, MedCPT reranker, policy,
    # retrieval gate, output checker, audit logger, and history handling.
    return GuardedChatbot.from_config(retriever=retriever, generator=generator)


def print_debug(debug: dict) -> None:
    print("\n--- debug ---")
    for key, value in debug.items():
        if value in (None, [], {}, ""):
            continue
        if key == "llm_draft":
            print(f"llm_draft:\n  {value}")
        elif key == "dropped_sentences":
            print("dropped_sentences:")
            for dropped in value:
                print(f"  [{dropped['reason']}] {dropped['sentence']}")
        elif isinstance(value, dict):
            print(f"{key}:")
            for name, field in value.items():
                print(f"  {name}: {field}")
        else:
            print(f"{key}: {value}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Guarded medical RAG chat (local Ollama by default)")
    ap.add_argument("question", nargs="?", help="a single question, or an initial question for --chat")
    ap.add_argument("--chat", action="store_true", help="keep one chatbot running for multiple turns")
    ap.add_argument("--trace", action="store_true", help="show decision and latency trace")
    ap.add_argument("--debug", action="store_true", help="show guardrail decisions and blocked output")
    ap.add_argument("--baseline", action="store_true", help="use original BM25 + extractive generator")
    ap.add_argument("--model", default=DEFAULT_LANGUAGE_MODEL, help="Ollama generation model (RAG mode)")
    ap.add_argument("--timeout", type=float, default=600.0, help="Ollama generation timeout in seconds")
    args = ap.parse_args()

    if not args.chat and not args.question:
        ap.error("give a question or use --chat")
    if args.timeout <= 0:
        ap.error("--timeout must be positive")

    try:
        bot = build_chatbot(baseline=args.baseline, model=args.model, timeout=args.timeout)
    except FileNotFoundError as exc:
        ap.exit(2, f"Setup error: {exc}\n")

    history: list[dict] = []
    question = args.question
    while True:
        if question is None:
            try:
                question = input("\nyou> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
        if not question:
            break

        # One GuardedChatbot handles every turn, preserving safety and context.
        response = bot.ask(question, history=list(history))
        print(f"[{response.action.value}]\n\n{response.text}")
        if args.debug:
            print_debug(response.debug)
        if args.trace:
            print("\n" + json.dumps(response.trace.to_dict(), indent=2))

        if not args.chat:
            break
        history.extend([
            {"role": "user", "content": question},
            {"role": "assistant", "content": response.text},
        ])
        question = None


if __name__ == "__main__":
    main()
