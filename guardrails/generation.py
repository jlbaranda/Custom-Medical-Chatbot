from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Protocol

from .normalize import content_tokens, normalize
from .types import Passage


# The answer generator sits between layer 4 and layer 5. The guardrails only need
# its contract: answer from the numbered passages, cite each sentence as [n].
# Until the team's Qwen model is wired in, ExtractiveGenerator "pretends" by
# quoting the most relevant source sentences, which keeps the pipeline testable.

SYSTEM_PROMPT = """You are a medical information assistant that answers general health questions using ONLY the numbered trusted medical sources provided.
Rules:
- Answer the user's specific question directly.
- Provide clear, useful explanations rather than brief summaries.
- Prioritize the most relevant information.
- Avoid repeating information unnecessarily.
- Organize information logically using short paragraphs.
- Use bullet points when listing symptoms, causes, or triggers.
- Explain relevant medical terms in simple language.
- Give enough detail to understand the topic, usually
  4-6 informative sentences, but adjust to the question.
- Never add medical claims that are not supported by the sources.
- Cite every factual sentence using its supporting source
  number, such as [1] or [2].
- If the sources do not sufficiently answer the question,
  reply exactly: NO_SUPPORT
- Do not diagnose, recommend personalized treatments,
  or provide medication doses.
- Do not make assumptions about the user's health.
- Avoid unnecessary introductory phrases and repetition.
- Use natural punctuation without spaces before periods.
- For a routine informational question, focus on about 4-6 informative sentences; use more detail when a comparison or the user asks for it.
- Answer the specific question first; do not repeat a previous answer's symptom list when the user asks about causes, tests, or triggers.
- Cite medical claims in EACH bullet point, not just once at the end of a list.
- Step 3: concise, non-repetitive answers:
  Answer the exact question immediately. For routine questions, use roughly
  4-6 information-rich sentences, or a short intro followed by up to 4 bullets.
  Do NOT repeat the same information both in a paragraph and in a bullet list.
  Prefer a short paragraph for simple questions; use bullets for clear lists.
  For comparisons, explain EACH condition and then contrast the key differences,
  grounding each condition in its own provided cited sources.
  Only include medically relevant details supported by the retrieved passages.
  Keep each factual sentence and each medical bullet independently cited.
  Do not claim permanence or certainty beyond what the sources establish."""

_SENTENCE = re.compile(r"(?<=[.!?\]])\s+(?=[A-Z0-9\"'(])")


def split_sentences(text: str) -> list[str]:
    return [
        s.strip()
        for s in _SENTENCE.split(text.strip())
        if s.strip()
    ]


def format_sources(passages: list[Passage]) -> str:
    return "\n\n".join(
        f"[{k}] {p.title} ({p.publisher})\n{p.text}"
        for k, p in enumerate(passages, 1)
    )


class Generator(Protocol):
    name: str

    def generate(
            self,
            question: str,
            passages: list[Passage],
    ) -> str:
        ...


class ExtractiveGenerator:
    name = "extractive-mock"

    def __init__(self, max_sentences: int = 4):
        self.max_sentences = max_sentences

    def generate(
            self,
            question: str,
            passages: list[Passage],
    ) -> str:
        q = set(content_tokens(normalize(question)))
        scored = []

        for k, p in enumerate(passages, 1):
            for pos, sent in enumerate(
                    split_sentences(
                        p.text.replace("\n", " ")
                    )
            ):
                words = content_tokens(sent)

                if not 6 <= len(words) <= 60:
                    continue

                overlap = (
                        len(q & set(words))
                        / (len(q) or 1)
                )

                scored.append(
                    (
                        overlap - 0.01 * pos,
                        k,
                        sent,
                    )
                )

        scored.sort(reverse=True)

        picked = [
            (k, s)
            for score, k, s in scored[: self.max_sentences]
            if score > 0
        ]

        if not picked:
            return "NO_SUPPORT"

        return " ".join(
            f"{s.rstrip('.')}. [{k}]"
            for k, s in picked
        )


def _output_tokens() -> int:
    """Token budget for local CPU generation; configurable without code edits."""
    raw = os.environ.get("MEDICAL_MAX_OUTPUT_TOKENS", "320")
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError("MEDICAL_MAX_OUTPUT_TOKENS must be an integer") from exc
    if not 128 <= value <= 2048:
        raise ValueError("MEDICAL_MAX_OUTPUT_TOKENS must be between 128 and 2048")
    return value


class OllamaGenerator:
    """Local Qwen (or any Ollama model). Optional: only used when configured."""

    def __init__(
            self,
            model: str = "qwen2.5:3b",
            host: str = "http://localhost:11434",
            timeout: float = 120,
    ):
        self.name = f"ollama:{model}"
        self.model = model
        self.host = host
        self.timeout = timeout

    def generate(
            self,
            question: str,
            passages: list[Passage],
    ) -> str:
        body = {
            "model": self.model,
            "stream": False,

            # Qwen3.5 supports thinking, but for this RAG pipeline
            # we want the final grounded answer directly.
            "think": False,
            "keep_alive": "30m",
            "options": {
                "temperature": 0.1,
                "num_predict": _output_tokens(),
            },

            "messages": [
                {
                    "role": "system",
                    "content": (
                            SYSTEM_PROMPT
                            + "\n\nSources:\n"
                            + format_sources(passages)
                    ),
                },
                {
                    "role": "user",
                    "content": question,
                },
            ],
        }

        req = urllib.request.Request(
            f"{self.host}/api/chat",
            data=json.dumps(body).encode(),
            headers={
                "Content-Type": "application/json",
            },
        )

        with urllib.request.urlopen(
                req,
                timeout=self.timeout,
        ) as resp:
            data = json.loads(resp.read())

        message = data.get("message", {})
        content = message.get("content", "").strip()

        if not content:
            raise RuntimeError(
                "Ollama returned an empty assistant response. "
                f"Response message keys: {list(message.keys())}"
            )

        return content