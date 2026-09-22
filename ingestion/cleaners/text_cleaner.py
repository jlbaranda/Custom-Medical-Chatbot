from __future__ import annotations

import html
import re

# Exact/near-exact UI lines that frequently leak out of government health pages.
# These are intentionally conservative. They target interface/navigation labels,
# not medical prose.
BOILERPLATE_LINE_PATTERNS = [
    r"skip to main content",
    r"print",
    r"share",
    r"facebook",
    r"linkedin",
    r"twitter",
    r"x \(twitter\)",
    r"syndicate",
    r"back to top",
    r"about this page",
    r"sources and page info",
    r"content source",
    r"keep reading",
    r"download",
    r"related links",
    r"additional resources(?: for .*)?",
    r"page last reviewed.*",
]
_BOILERPLATE_RE = re.compile(
    r"^(?:" + "|".join(BOILERPLATE_LINE_PATTERNS) + r")\s*$",
    flags=re.IGNORECASE,
)


def repair_text_encoding(text: str) -> str:
    """Repair common UTF-8/Windows-1252 mojibake conservatively.

    v4 prevents most encoding damage by parsing raw response bytes. This
    function is a final safety net for text that is already damaged before it
    reaches the cleaner.  Replacements are deliberately limited to common
    reversible punctuation sequences seen on the government pages in this
    corpus.
    """
    value = text or ""
    replacements = {
        "â€™": "’",
        "â€˜": "‘",
        "â€œ": "“",
        "â€�": "”",
        "â€”": "—",
        "â€“": "–",
        "â€¦": "…",
        "â€³": "″",
        "â€²": "′",
        "Â ": " ",
        "Â ": " ",
    }
    for broken, fixed in replacements.items():
        value = value.replace(broken, fixed)

    # A second conservative attempt repairs strings/lines that are entirely
    # representable as cp1252.  We only keep the result when it reduces known
    # mojibake markers.
    markers = ("â€", "â€™", "â€œ", "â€�", "â€”", "â€“", "Ã", "Â")

    def badness(s: str) -> int:
        return sum(s.count(marker) for marker in markers)

    repaired_lines: list[str] = []
    for line in value.splitlines(keepends=True):
        if not any(marker in line for marker in markers):
            repaired_lines.append(line)
            continue
        try:
            candidate = line.encode("cp1252").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            repaired_lines.append(line)
            continue
        repaired_lines.append(candidate if badness(candidate) < badness(line) else line)

    return "".join(repaired_lines)


def _remove_boilerplate_lines(text: str) -> str:
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            lines.append("")
            continue
        if _BOILERPLATE_RE.match(line):
            continue
        lines.append(line)
    return "\n".join(lines)


def clean_text(text: str) -> str:
    """Normalize extracted article/PDF text without changing its meaning."""
    text = html.unescape(text or "")
    text = repair_text_encoding(text)
    text = text.replace("\xa0", " ")
    text = _remove_boilerplate_lines(text)

    # Keep paragraph/heading boundaries but normalize whitespace within lines.
    normalized_lines: list[str] = []
    for line in text.splitlines():
        line = re.sub(r"[ \t]+", " ", line).strip()
        # HTML inline elements can introduce a separator before punctuation
        # (for example: "disease </a>." -> "disease ."). Remove only
        # whitespace immediately before ordinary punctuation.
        line = re.sub(r"\s+([,.;:!?])", r"\1", line)
        normalized_lines.append(line)
    text = "\n".join(normalized_lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
