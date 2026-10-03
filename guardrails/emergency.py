from __future__ import annotations

import re
from dataclasses import dataclass

# Emergency detection is tuned for recall: a missed emergency is the worst failure
# mode of the whole system, a false alarm only costs one extra banner.
#
# Tiers:
#   active        - someone appears to be experiencing it now -> emergency response only
#   informational - asks *about* an emergency ("signs of a stroke") -> answer, banner first
#   None

_SYMPTOMS: dict[str, str] = {
    "cardiac": r"chest (?:pain|pressure|tightness|hurts?)|heart attack|crushing (?:pain|pressure)|pain (?:in|down) my (?:left )?arm",
    "breathing": r"(?:can ?not|cannot|can't|unable to|hard to|struggling to|trouble|difficulty) (?:breath|breathe|breathing)"
                 r"|not breathing|stopped breathing|choking|gasping|turning blue|lips (?:are )?blue",
    "stroke": r"stroke|face (?:is )?droop|slurr?ed speech|(?:one|left|right) side (?:of (?:my|his|her|their) body )?(?:is )?(?:numb|weak)"
              r"|sudden (?:numbness|weakness|confusion|severe headache)|worst headache of (?:my|his|her) life",
    "anaphylaxis": r"throat (?:is )?(?:closing|swelling|tight)|tongue (?:is )?swelling|lips (?:are )?swelling|anaphyla",
    "bleeding": r"(?:heavy|severe|won'?t stop|will not stop|uncontrolled) bleeding|bleeding (?:heavily|a lot|won'?t stop|will not stop)"
                r"|coughing (?:up )?blood|vomiting blood",
    "consciousness": r"unconscious|unresponsive|passed out|won'?t wake up|will not wake up|not waking up|fainted and",
    "seizure": r"(?:having|having a|is having a|in) (?:a )?seizure|seizing|convuls",
    "overdose": r"overdos|took (?:too many|a whole bottle|the whole bottle|all (?:of )?(?:my|the|his|her))|swallowed (?:a bottle|bleach|poison|pills|batteries)"
                r"|drank (?:bleach|antifreeze)|poison(?:ed|ing)",
    "glucose": r"blood sugar (?:is )?(?:very |super |really )?(?:low|crashing|below \d+)|(?:sugar|glucose) (?:of|is|at) (?:[1-4]\d|[5-9])\b|diabetic coma|dka",
    "general": r"\b911\b|ambulance|(?:i am|i'm|he is|she is|they are) dying|going to die|life.threatening",
}
_SELF_HARM = (
    r"kill (?:my ?self|myself)|suicid|end (?:my|it all|my life)|want to die|wanna die|don't want to (?:live|be alive)"
    r"|do not want to (?:live|be alive)|hurt(?:ing)? my ?self|harm(?:ing)? my ?self|self.harm|cut(?:ting)? my ?self|\bkms\b"
    r"|not worth living|lethal (?:dose|amount)|(?:how much|how many).{0,40}(?:to die|to kill|be fatal|is fatal|would kill)"
    r"|(?:fatal|deadly) (?:dose|amount)"
)

_SYMPTOM_RE = {k: re.compile(v) for k, v in _SYMPTOMS.items()}
_SELF_HARM_RE = re.compile(_SELF_HARM)

# Signals that a real person is involved, now.
_ACTIVE = re.compile(
    r"\b(?:i|i am|i have|me|my|we|our|he|she|they|his|her|their|someone|somebody|mom|mother|dad|father|son|daughter|"
    r"husband|wife|friend|baby|child|kid|toddler|grandma|grandpa|partner|coworker)\b"
    r"|\b(?:now|right now|currently|just now|happening|hurry|asap|please help|help me)\b"
)
# A question with no person in it is about the topic, not an event.
_QUESTION = re.compile(r"^(?:what|how|why|when|which|who|whats|are|is|does|do|can|could|list|explain|tell me|describe)\b")
# Families that are only "active" when a person is mentioned; bare mentions are educational.
_NEEDS_PERSON = {"overdose", "general", "anaphylaxis"}
_NEGATION = re.compile(r"\b(?:no|not|never|don't|do not|without|denies|isn't|wasn't|no longer)\b(?:\s+\w+){0,3}\s*$")


@dataclass(frozen=True)
class EmergencyResult:
    tier: str | None  # "active", "informational", None
    kind: str | None  # symptom family, or "self_harm"
    score: float
    reason: str = ""


def _negated(text: str, start: int) -> bool:
    return bool(_NEGATION.search(text[max(0, start - 30):start]))


def detect_emergency(text: str) -> EmergencyResult:
    """`text` should already be normalize()d."""
    if m := _SELF_HARM_RE.search(text):
        # Self-harm is always treated as active: asking "how much X is lethal" is itself the signal.
        if not _negated(text, m.start()) or "lethal" in m.group(0) or "fatal" in m.group(0):
            return EmergencyResult("active", "self_harm", 1.0, f"self_harm:{m.group(0)}")

    hits = []
    for kind, pattern in _SYMPTOM_RE.items():
        for m in pattern.finditer(text):
            hits.append((kind, m, _negated(text, m.start())))
    if not hits:
        return EmergencyResult(None, None, 0.0)

    positive = [(k, m) for k, m, neg in hits if not neg]
    if not positive:
        # Every mention negated ("no chest pain") -> still show the banner.
        kind, m, _ = hits[0]
        return EmergencyResult("informational", kind, 0.4, f"negated:{m.group(0)}")

    kind, m = positive[0]
    if _ACTIVE.search(text):
        return EmergencyResult("active", kind, 0.95, f"active:{m.group(0)}")
    if _QUESTION.search(text) or kind in _NEEDS_PERSON:
        return EmergencyResult("informational", kind, 0.5, f"informational:{m.group(0)}")
    # Bare symptom phrase with no framing ("chest pain left arm numb") -> assume active.
    return EmergencyResult("active", kind, 0.8, f"bare:{m.group(0)}")


EMERGENCY_HEADER = (
    "**If you or someone else may be having a medical emergency, call 911 (or your local emergency number) now.**"
)
_KIND_LINES = {
    "self_harm": (
        "You can call or text **988** (Suicide & Crisis Lifeline, US) any time to talk with someone right now. "
        "If you are in immediate danger, call 911."
    ),
    "overdose": "For a possible poisoning or overdose, call **Poison Control at 1-800-222-1222** (US) if the person is awake and breathing; call 911 if not.",
    "anaphylaxis": "If an epinephrine auto-injector has been prescribed, use it as directed and call 911.",
    "stroke": "Note the time symptoms started; emergency teams need it.",
    "cardiac": "Do not drive yourself to the hospital; call 911 so treatment can start on the way.",
}


def emergency_response(result: EmergencyResult) -> str:
    if result.kind == "self_harm":
        return "I'm really sorry you're dealing with this. " + _KIND_LINES["self_harm"] + \
            "\n\nI can't help with this question, but people at 988 can, right now."
    lines = [EMERGENCY_HEADER]
    if result.kind in _KIND_LINES:
        lines.append(_KIND_LINES[result.kind])
    lines.append("This assistant cannot assess emergencies. Please contact emergency services before anything else.")
    return "\n\n".join(lines)
