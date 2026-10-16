"""Ask the guarded chatbot from the command line.

    python scripts/ask.py "what are the symptoms of anemia"
    python scripts/ask.py --trace "how much tylenol for my 3 year old"
    python scripts/ask.py --chat          # multi-turn conversation, empty line to quit
    python scripts/ask.py --debug "..."   # which guardrail fired, probabilities, blocked LLM draft
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from guardrails import GuardedChatbot  # noqa: E402


def print_debug(debug: dict) -> None:
    print("\n--- debug ---")
    for key, value in debug.items():
        if value in (None, [], {}, ""):
            continue
        if key == "llm_draft":
            print(f"llm_draft:\n  {value}")
        elif key == "dropped_sentences":
            print("dropped_sentences:")
            for d in value:
                print(f"  [{d['reason']}] {d['sentence']}")
        elif isinstance(value, dict):
            print(f"{key}:")
            for k, v in value.items():
                print(f"  {k}: {v}")
        else:
            print(f"{key}: {value}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("question", nargs="?")
    ap.add_argument("--trace", action="store_true", help="print the decision trace")
    ap.add_argument("--chat", action="store_true", help="multi-turn conversation")
    ap.add_argument("--debug", action="store_true", help="show which guardrail fired and why")
    args = ap.parse_args()
    if not args.chat and not args.question:
        ap.error("give a question or use --chat")
    bot = GuardedChatbot.from_config()
    history: list[dict] = []
    question = args.question
    while True:
        if question is None:
            question = input("\nyou> ").strip()
        if not question:
            break
        r = bot.ask(question, history=history)
        print(f"[{r.action.value}]\n\n{r.text}")
        if args.debug:
            print_debug(r.debug)
        if args.trace:
            print("\n" + json.dumps(r.trace.to_dict(), indent=2))
        if not args.chat:
            break
        history += [{"role": "user", "content": question}, {"role": "assistant", "content": r.text}]
        question = None


if __name__ == "__main__":
    main()
