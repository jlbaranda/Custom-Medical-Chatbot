from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse


SPANISH_PATH_PATTERNS = (
    "/spanish/",
    "/espanol/",
    "/español/",
)


def normalize_language(value: str | None) -> str:
    return (value or "").strip().lower().replace("_", "-")


def is_english_language(value: str | None) -> bool:
    language = normalize_language(value)
    return language in {"english", "en"} or language.startswith("en-")


def is_spanish_language(value: str | None) -> bool:
    language = normalize_language(value)
    return language in {"spanish", "es", "espanol", "español"} or language.startswith("es-")


def is_obviously_spanish_url(url: str) -> bool:
    if not url:
        return False

    parsed = urlparse(url)
    path = (parsed.path or "").lower()
    if any(pattern in path for pattern in SPANISH_PATH_PATTERNS):
        return True

    # A path whose first segment is exactly /es/... is usually a locale path.
    if re.match(r"^/es(?:/|$)", path):
        return True

    query = {key.lower(): [v.lower() for v in values] for key, values in parse_qs(parsed.query).items()}
    for key in ("lang", "language", "locale"):
        if any(value == "es" or value.startswith("es-") for value in query.get(key, [])):
            return True

    return False


def header_language(headers) -> str:
    return (headers.get("Content-Language") or "").split(",", 1)[0].strip()


def html_declares_spanish(html: str | bytes) -> bool:
    if not html:
        return False
    if isinstance(html, bytes):
        # HTML tags/attributes are ASCII-compatible.  We only need enough text
        # to inspect <html lang=...>; ignoring non-ASCII bytes is safe here.
        html = html[:16384].decode("ascii", errors="ignore")
    match = re.search(r"<html\b[^>]*\blang\s*=\s*['\"]?([^'\"\s>]+)", html, flags=re.IGNORECASE)
    return bool(match and is_spanish_language(match.group(1)))
