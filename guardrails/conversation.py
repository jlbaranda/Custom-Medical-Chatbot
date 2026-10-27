from __future__ import annotations

import re

# Multi-turn support: history uses standard {role, content} dictionaries.
# A complete, explicitly scoped question is NOT a follow-up merely because it
# happens to be short (e.g. "How is asthma diagnosed?").
#
# Safety: the pipeline still screens each user message, checks recent turns for
# emergencies, and screens combined history for genuinely dependent follow-ups.

_CONTEXT_OPENER = re.compile(
    r"^(?:and|or|so|but|ok|okay|then|also|what about|how about|what if|same)\b"
)

# Pronouns whose meaning normally depends on prior dialogue. Do not include
# 'I', 'me', 'my', or 'you', which often appear in standalone medical questions.
_CONTEXT_REFERENCE = re.compile(
    r"\b(?:it|its|that|this|those|these|them|they|he|she|him|her|one|ones)\b"
)

# Brief fragments whose topic is omitted, as opposed to complete, short
# questions such as "What causes asthma attacks?".
_TOPIC_FRAGMENT = re.compile(
    r"^(?:(?:more|details?|examples?|symptoms?|causes?|triggers?|"
    r"treatments?|risks?|side effects?|prevention|diagnosis|"
    r"for (?:kids|children|adults|women|men|seniors))"
    r"|(?:why|how|when|where|which one|what now))\s*[?!.]*$"
)


def user_turns(history: list[dict] | None) -> list[str]:
    return [t["content"] for t in history or [] if t.get("role") == "user" and t.get("content")]


def is_follow_up(normalized_text: str) -> bool:
    """Whether a question needs previous user turns to make sense.

    The input is already normalized by guardrails.normalize.normalize().
    This is a conservative heuristic, not a full coreference resolver.
    """
    text = normalized_text.strip()
    if not text:
        return False
    return bool(
        _CONTEXT_OPENER.search(text)
        or _CONTEXT_REFERENCE.search(text)
        or _TOPIC_FRAGMENT.fullmatch(text)
    )
