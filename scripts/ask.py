"""Ask the guarded chatbot one question from the command line.

    python scripts/ask.py "what are the symptoms of anemia"
    python scripts/ask.py --trace "how much tylenol for my 3 year old"
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from guardrails import GuardedChatbot  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("--trace", action="store_true", help="print the decision trace")
    args = ap.parse_args()
    bot = GuardedChatbot.from_config()
    r = bot.ask(args.question)
    print(f"[{r.action.value}]\n\n{r.text}")
    if args.trace:
        print("\n" + json.dumps(r.trace.to_dict(), indent=2))


if __name__ == "__main__":
    main()
