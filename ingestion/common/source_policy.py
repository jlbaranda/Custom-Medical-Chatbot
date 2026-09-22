from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse


# Version 1 is deliberately conservative. MedlinePlus is used as a discovery
# layer; only candidates from these source families become full documents.
TRUSTED_DOMAIN_ROOTS = {
    "medlineplus.gov": {
        "publisher_parent": "National Library of Medicine",
        "source_group": "medlineplus",
    },
    "nih.gov": {
        "publisher_parent": "National Institutes of Health",
        "source_group": "nih",
    },
    "cdc.gov": {
        "publisher_parent": "Centers for Disease Control and Prevention",
        "source_group": "cdc",
    },
    "cancer.gov": {
        "publisher_parent": "National Cancer Institute",
        "source_group": "nci",
    },
}


@dataclass(frozen=True)
class TrustDecision:
    allowed: bool
    reason: str
    matched_domain: str | None = None
    publisher_parent: str | None = None
    source_group: str | None = None


def normalize_host(url: str) -> str:
    host = (urlparse(url).hostname or "").lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    return host


def _is_same_or_subdomain(host: str, root: str) -> bool:
    return host == root or host.endswith("." + root)


def evaluate_trusted_source(url: str) -> TrustDecision:
    host = normalize_host(url)
    if not host:
        return TrustDecision(False, "invalid_url")

    for root, metadata in TRUSTED_DOMAIN_ROOTS.items():
        if _is_same_or_subdomain(host, root):
            return TrustDecision(
                True,
                "trusted_government_domain",
                matched_domain=root,
                publisher_parent=metadata["publisher_parent"],
                source_group=metadata["source_group"],
            )

    return TrustDecision(False, "domain_not_allowlisted")
