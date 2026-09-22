from __future__ import annotations

from urllib.parse import urlparse

from ingestion.common.source_policy import evaluate_trusted_source


def resolve_publisher(url: str, publisher_hints: list[str] | None = None) -> dict:
    """Return citation/source metadata for the actual page publisher.

    MedlinePlus may have discovered the URL, but the citation should name the
    organization that actually publishes the page whenever that information is
    available.
    """
    trust = evaluate_trusted_source(url)
    host = (urlparse(url).hostname or "").lower()
    hints = [value.strip() for value in (publisher_hints or []) if value.strip()]

    publisher = hints[0] if hints else (trust.publisher_parent or host)

    return {
        "publisher": publisher,
        "publisher_parent": trust.publisher_parent or "",
        "source_domain": host,
        "trusted_domain": trust.matched_domain or "",
        "source_group": trust.source_group or "web",
    }
