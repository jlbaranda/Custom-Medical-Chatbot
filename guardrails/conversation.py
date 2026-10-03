from __future__ import annotations

import re

from .normalize import tokens

# Multi-turn support. History is the usual chat format:
#   [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}, ...]
# Only user turns are used by the guardrails; assistant text is never re-screened.

# A message that leans on earlier turns: very short, opens with a connective, or refers
# back with a pronoun ("what about for kids", "how many of those", "and for him").
_FOLLOW_UP = re.compile(
    r"^(?:and|or|so|but|ok|okay|then|also|what about|how about|what if|same)\b"
    r"|\b(?:it|its|that|this|those|these|them|they|he|she|him|her|one|ones)\b"
)
SHORT_MESSAGE_TOKENS = 6


def user_turns(history: list[dict] | None) -> list[str]:
    return [t["content"] for t in history or [] if t.get("role") == "user" and t.get("content")]


def is_follow_up(normalized_text: str) -> bool:
    return len(tokens(normalized_text)) <= SHORT_MESSAGE_TOKENS or bool(_FOLLOW_UP.search(normalized_text))
