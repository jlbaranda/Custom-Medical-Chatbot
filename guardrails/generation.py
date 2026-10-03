from __future__ import annotations

import json
import re
import urllib.request
from typing import Protocol

from .normalize import content_tokens, normalize
from .types import Passage

# The answer generator sits between layer 4 and layer 5. The guardrails only need
# its contract: answer from the numbered passages, cite each sentence as [n].
# Until the team's Qwen model is wired in, ExtractiveGenerator "pretends" by
# quoting the most relevant source sentences, which keeps the pipeline testable.

SYSTEM_PROMPT = """You answer general health questions using ONLY the numbered sources below.
Rules:
- End every sentence with the source number it comes from, like [1] or [2].
- If the sources do not answer the question, reply exactly: NO_SUPPORT
- Do not diagnose, do not give doses or amounts, do not tell the reader what they personally should take or stop.
- Plain language, at most 5 sentences."""

_SENTENCE = re.compile(r"(?<=[.!?\]])\s+(?=[A-Z0-9\"'(])")


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE.split(text.strip()) if s.strip()]


def format_sources(passages: list[Passage]) -> str:
    return "\n\n".join(f"[{k}] {p.title} ({p.publisher})\n{p.text}" for k, p in enumerate(passages, 1))


class Generator(Protocol):
    name: str

    def generate(self, question: str, passages: list[Passage]) -> str: ...


class ExtractiveGenerator:
    name = "extractive-mock"

    def __init__(self, max_sentences: int = 4):
        self.max_sentences = max_sentences

    def generate(self, question: str, passages: list[Passage]) -> str:
        q = set(content_tokens(normalize(question)))
        scored = []
        for k, p in enumerate(passages, 1):
            for pos, sent in enumerate(split_sentences(p.text.replace("\n", " "))):
                words = content_tokens(sent)
                if not 6 <= len(words) <= 60:
                    continue
                overlap = len(q & set(words)) / (len(q) or 1)
                scored.append((overlap - 0.01 * pos, k, sent))
        scored.sort(reverse=True)
        picked = [(k, s) for score, k, s in scored[: self.max_sentences] if score > 0]
        if not picked:
            return "NO_SUPPORT"
        return " ".join(f"{s.rstrip('.')}. [{k}]" for k, s in picked)


class OllamaGenerator:
    """Local Qwen (or any Ollama model). Optional: only used when configured."""

    def __init__(self, model: str = "qwen2.5:3b", host: str = "http://localhost:11434", timeout: float = 120):
        self.name = f"ollama:{model}"
        self.model, self.host, self.timeout = model, host, timeout

    def generate(self, question: str, passages: list[Passage]) -> str:
        body = {
            "model": self.model,
            "stream": False,
            "options": {"temperature": 0.1},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT + "\n\nSources:\n" + format_sources(passages)},
                {"role": "user", "content": question},
            ],
        }
        req = urllib.request.Request(f"{self.host}/api/chat", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read())["message"]["content"]
