from __future__ import annotations

from .types import Intent, Passage

_SEE = "a doctor, nurse, or pharmacist who can look at your full situation"

DECLINE = {
    Intent.DIAGNOSIS: f"I can't tell what condition someone has or interpret personal symptoms or results. Please ask {_SEE}.",
    Intent.DOSING: "I can't give doses or amounts. A pharmacist or the prescriber can give the right dose, and the "
                   "medicine's label lists the approved directions.",
    Intent.TREATMENT_DECISION: f"I can't advise whether to take, stop, or change a treatment. Please check with {_SEE} "
                               "before making a change.",
}
REDIRECT_INTRO = "Here is general information from trusted sources that may help you prepare questions for them:"
NO_SUPPORT = ("I couldn't find this in my trusted sources (MedlinePlus, NIH, CDC), so I won't guess. "
              "A healthcare professional or MedlinePlus.gov is a good place to ask.")
INFO_BANNER = "If this is happening to someone right now, call 911 (or your local emergency number)."
FOOTER = "General information only, not medical advice."


def sources_block(passages: list[Passage]) -> str:
    return "\n".join(f"[{k}] {p.title} ({p.publisher}) {p.source_url}" for k, p in enumerate(passages, 1))


def compose(body: str, sources: list[Passage], *, decline: str | None = None, banner: bool = False) -> str:
    parts = []
    if banner:
        parts.append(f"**{INFO_BANNER}**")
    if decline:
        parts.append(decline)
        parts.append(REDIRECT_INTRO)
    parts.append(body)
    parts.append("Sources:\n" + sources_block(sources))
    parts.append(f"_{FOOTER}_")
    return "\n\n".join(parts)


