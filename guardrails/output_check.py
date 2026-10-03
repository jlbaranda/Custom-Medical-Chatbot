from __future__ import annotations

import re
from dataclasses import dataclass, field

from .generation import split_sentences
from .normalize import content_tokens
from .types import Passage

# Layer 5: every sentence that survives must (a) cite a retrieved passage,
# (b) be lexically supported by that passage, (c) only contain numbers that appear
# in that passage, and (d) contain no dose amounts, diagnoses of the reader, or
# personal directives. Failing sentences are dropped, not rewritten.

_CITE = re.compile(r"\[(\d+)\]")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
_DOSE = re.compile(
    r"\b\d+(?:[.,]\d+)?\s*(?:-|to)?\s*\d*\s*(?:mg|mcg|µg|micrograms?|milligrams?|grams?|g|ml|milliliters?|units?|iu|"
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


@dataclass
class OutputCheck:
    kept: list[tuple[str, list[int]]] = field(default_factory=list)
    dropped: dict[str, int] = field(default_factory=dict)

    def drop(self, reason: str) -> None:
        self.dropped[reason] = self.dropped.get(reason, 0) + 1

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

    for sentence in split_sentences(answer.replace("\n", " ")):
        cites = [int(n) for n in _CITE.findall(sentence)]
        bare = _CITE.sub("", sentence).strip()
        if not content_tokens(bare):
            continue
        valid = [n for n in cites if 1 <= n <= len(passages)]
        if not valid:
            result.drop("uncited" if not cites else "bad_citation")
            continue
        source_text = " ".join(passages[n - 1].text for n in valid)
        source_tokens = set(content_tokens(source_text))
        words = content_tokens(bare)
        support = sum(w in source_tokens for w in words) / len(words)
        if support < min_support:
            result.drop("unsupported")
            continue
        if any(num not in source_text for num in _NUMBER.findall(bare)):
            result.drop("number_not_in_source")
            continue
        if block_doses and _DOSE.search(bare):
            result.drop("dose")
            continue
        if _PERSONAL_CLAIM.search(bare):
            result.drop("personal_claim")
            continue
        result.kept.append((bare, valid))
    return result


def render(check: OutputCheck, passages: list[Passage]) -> tuple[str, list[Passage]]:
    """Renumber citations to the passages actually used and return (text, sources)."""
    used = check.cited_ids
    remap = {old: new for new, old in enumerate(used, 1)}
    body = " ".join(s.rstrip() + " " + "".join(f"[{remap[n]}]" for n in ns) for s, ns in check.kept)
    return body.strip(), [passages[n - 1] for n in used]
