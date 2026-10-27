from __future__ import annotations

import re
from dataclasses import dataclass, field

from .generation import split_sentences
from .normalize import content_tokens
from .types import Passage

# Layer 5 still checks each sentence for valid citations, lexical grounding,
# source-supported numbers, disallowed doses, and personal medical claims.
# Layout is restored ONLY after the same checks that were applied previously.
_CITE = re.compile(r"\[(\d+)\]")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
_BULLET = re.compile(r"^\s*(?:[-*\u2022]|\d+[.)])\s+")
_DOSE = re.compile(
    r"\b\d+(?:[.,]\d+)?\s*(?:-|to)?\s*\d*\s*(?:mg|mcg|\u00b5g|micrograms?|milligrams?|grams?|g|ml|milliliters?|units?|iu|"
    r"tablets?|pills?|capsules?|puffs?|drops?|teaspoons?|tsp|tablespoons?|doses?)\b"
    r"|\b(?:once|twice|three times|four times|\d+ times) (?:a|per) day\b|\bevery \d+(?:\s*(?:-|to)\s*\d+)? hours\b",
    re.I,
)
_PERSONAL_CLAIM = re.compile(
    r"\byou (?:likely |probably |may |might |could |definitely )?(?:have|are suffering from|are having|have got)\b"
    r"|\byou(?:'re| are) (?:diabetic|anemic|asthmatic|hypothyroid|pregnant)\b"
    r"|\byou should (?:take|stop|start|increase|decrease|double|skip|switch|not take)\b"
    r"|\b(?:take|give) (?:\d|one|two|three|half)\b",
    re.I,
)


def _tidy_punctuation(text: str) -> str:
    """Remove whitespace left before punctuation when [n] citations are stripped."""
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    return re.sub(r"[ \t]+", " ", text).strip()


@dataclass
class OutputCheck:
    # Keep the original (sentence, cited passage ids) API for other guardrails.
    kept: list[tuple[str, list[int]]] = field(default_factory=list)
    dropped: dict[str, int] = field(default_factory=dict)
    dropped_sentences: list[tuple[str, str]] = field(default_factory=list)
    # A layout marker parallel to kept: paragraph, bullet, or inline.
    layout: list[str] = field(default_factory=list)

    def drop(self, reason: str, sentence: str = "") -> None:
        self.dropped[reason] = self.dropped.get(reason, 0) + 1
        if sentence:
            self.dropped_sentences.append((reason, sentence))

    @property
    def cited_ids(self) -> list[int]:
        return sorted({n for _, ns in self.kept for n in ns})

    def to_dict(self) -> dict:
        return {"kept": len(self.kept), "dropped": self.dropped}


def check_output(answer: str, passages: list[Passage], config: dict, action: str) -> OutputCheck:
    result = OutputCheck()
    if answer.strip().upper().startswith("NO_SUPPORT"):
        result.drop("model_no_support")
        return result

    block_doses = action in config["output"]["block_doses_in"]
    min_support = config["output"]["min_support"]
    require_citations = config["output"].get("require_citations", True)

    # Validate per line so each markdown bullet needs its OWN citation.
    # Do not accept an uncited heading as a free pass for medical claims.
    for original_line in answer.splitlines():
        line = original_line.strip()
        if not line:
            continue
        bullet = _BULLET.match(line)
        if bullet:
            line = line[bullet.end():].strip()
        first_kept_on_line = True
        for sentence in split_sentences(line):
            cites = [int(n) for n in _CITE.findall(sentence)]
            bare = _tidy_punctuation(_CITE.sub("", sentence))
            if not content_tokens(bare):
                continue
            valid = [n for n in cites if 1 <= n <= len(passages)]
            if not valid and require_citations:
                result.drop("uncited" if not cites else "bad_citation", sentence)
                continue
            # When citations are optional, keep the old behavior: check every passage.
            source_text = " ".join(passages[n - 1].text for n in valid or range(1, len(passages) + 1))
            source_tokens = set(content_tokens(source_text))
            words = content_tokens(bare)
            support = sum(w in source_tokens for w in words) / len(words)
            if support < min_support:
                result.drop("unsupported", sentence)
                continue
            if any(num not in source_text for num in _NUMBER.findall(bare)):
                result.drop("number_not_in_source", sentence)
                continue
            if block_doses and _DOSE.search(bare):
                result.drop("dose", sentence)
                continue
            if _PERSONAL_CLAIM.search(bare):
                result.drop("personal_claim", sentence)
                continue

            result.kept.append((bare, valid))
            result.layout.append("bullet" if first_kept_on_line and bullet else
                                 "paragraph" if first_kept_on_line else "inline")
            first_kept_on_line = False
    return result


def render(check: OutputCheck, passages: list[Passage]) -> tuple[str, list[Passage]]:
    """Renumber/dedupe cited sources, preserving validated paragraphs and bullets."""
    remap: dict[int, int] = {}
    sources: list[Passage] = []
    url_number: dict[str, int] = {}
    uncited = any(not ns for _, ns in check.kept)
    for n in check.cited_ids + (list(range(1, len(passages) + 1)) if uncited else []):
        url = passages[n - 1].source_url or passages[n - 1].chunk_id
        if url not in url_number:
            sources.append(passages[n - 1])
            url_number[url] = len(sources)
        remap[n] = url_number[url]

    # If filtering leaves just one bullet from a list, show it as an
    # ordinary paragraph instead of an orphaned, one-item list. We only
    # change presentation AFTER every sentence has passed the same checks.
    layout = [check.layout[i] if i < len(check.layout) else "inline"
              for i in range(len(check.kept))]
    for i, style in enumerate(layout):
        if style != "bullet":
            continue
        previous = next((layout[j] for j in range(i - 1, -1, -1)
                         if layout[j] != "inline"), None)
        following = next((layout[j] for j in range(i + 1, len(layout))
                          if layout[j] != "inline"), None)
        if previous != "bullet" and following != "bullet":
            layout[i] = "paragraph"

    lines: list[str] = []
    in_bullet_block = False
    for i, (sentence, ns) in enumerate(check.kept):
        cites = "".join(f"[{k}]" for k in sorted({remap[n] for n in ns}))
        text = _tidy_punctuation(sentence)
        if cites:
            text = f"{text} {cites}"
        style = layout[i]
        if i == 0:
            lines.append(("- " if style == "bullet" else "") + text)
        elif style == "bullet":
            lines.append(("\n" if in_bullet_block else "\n\n") + "- " + text)
        elif style == "paragraph":
            lines.append("\n\n" + text)
        else:
            lines.append(" " + text)
        if style == "bullet":
            in_bullet_block = True
        elif style == "paragraph":
            in_bullet_block = False
    return "".join(lines).strip(), sources
