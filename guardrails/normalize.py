from __future__ import annotations

import re
import unicodedata

# Undo cheap obfuscation used to slip past keyword rules: zero-width characters,
# homoglyphs (NFKC), leetspeak inside words ("d0se"), and spaced letters ("d o s e").

_ZERO_WIDTH = re.compile(r"[​-‏⁠﻿­]")
_LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s"})
_MIXED_TOKEN = re.compile(r"\b(?=[a-z0-9@$]*[a-z])(?=[a-z0-9@$]*[0-9@$])[a-z0-9@$]{3,}\b")
_UNITS = re.compile(r"^\d+(mg|mcg|ml|g|iu|units?|mmol|kg|lbs?|am|pm|x|st|nd|rd|th|s)$")
_SPACED = re.compile(r"\b(?:[a-z][ .\-_*]){2,}[a-z]\b")
_CONTRACTIONS = {
    "what's": "what is", "i'm": "i am", "i've": "i have", "i'd": "i would", "i'll": "i will",
    "can't": "cannot", "don't": "do not", "doesn't": "does not", "isn't": "is not",
    "shouldn't": "should not", "won't": "will not", "it's": "it is", "that's": "that is",
    "im": "i am", "ive": "i have", "whats": "what is", "dont": "do not", "cant": "cannot",
}
_CONTRACTION_RE = re.compile(r"\b(" + "|".join(re.escape(k) for k in _CONTRACTIONS) + r")\b")


def _deleet(match: re.Match) -> str:
    token = match.group(0)
    if _UNITS.match(token):  # keep "500mg", "2x", "3rd"
        return token
    return token.translate(_LEET)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = _ZERO_WIDTH.sub("", text).lower()
    text = text.replace("’", "'").replace("‘", "'")
    text = _MIXED_TOKEN.sub(_deleet, text)
    text = _SPACED.sub(lambda m: re.sub(r"[ .\-_*]", "", m.group(0)), text)
    text = _CONTRACTION_RE.sub(lambda m: _CONTRACTIONS[m.group(1)], text)
    return re.sub(r"\s+", " ", text).strip()


_WORD = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")

STOPWORDS = frozenset(
    "a an and are as at be been being but by can could did do does for from had has have how i if in "
    "into is it its me my of on or our should so than that the their them then there these they this "
    "to was we were what when where which who why will with would you your about any some more most "
    "also just get got am".split()
)


def tokens(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def content_tokens(text: str) -> list[str]:
    return [t for t in tokens(text) if t not in STOPWORDS and len(t) > 1]
