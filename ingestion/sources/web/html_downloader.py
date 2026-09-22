from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

from ingestion.cleaners.html_cleaner import extract_article_text
from ingestion.cleaners.pdf_cleaner import extract_pdf_text
from ingestion.common.language_filters import (
    header_language,
    html_declares_spanish,
    is_obviously_spanish_url,
    is_spanish_language,
)
from ingestion.common.source_policy import evaluate_trusted_source
from ingestion.sources.web.publishers import resolve_publisher

USER_AGENT = "medical-chatbot-ingestion/4.0 (educational project; respectful single-request crawler)"
DEFAULT_TIMEOUT = (10, 30)  # connect timeout, read timeout


@dataclass
class DownloadResult:
    status: str
    url: str
    reason: str = ""
    document_path: str = ""
    document_id: str = ""
    publisher: str = ""
    http_status: int | None = None
    content_type: str = ""
    source_format: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def stable_document_id(url: str) -> str:
    host = (urlparse(url).hostname or "document").replace("www.", "")
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    safe_host = re.sub(r"[^a-z0-9]+", "_", host.lower()).strip("_")
    return f"{safe_host}_{digest}"


def _suffix(url: str) -> str:
    return Path(urlparse(url).path).suffix.lower()


def _is_html(content_type: str, url: str) -> bool:
    ct = (content_type or "").lower()
    if "text/html" in ct or "application/xhtml+xml" in ct:
        return True
    return _suffix(url) in {"", ".html", ".htm"} and "pdf" not in ct


def _is_pdf(content_type: str, url: str) -> bool:
    ct = (content_type or "").lower()
    return "application/pdf" in ct or _suffix(url) == ".pdf"


def _output_dir_for_source(documents_root: Path, source_group: str) -> Path:
    allowed = {"medlineplus", "nih", "cdc", "nci"}
    group = source_group if source_group in allowed else "web"
    return documents_root / group


def _write_document(
    *,
    candidate: dict,
    documents_root: Path,
    final_url: str,
    original_url: str,
    title: str,
    text: str,
    source_format: str,
    content_type: str,
    final_trust,
    page_count: int | None = None,
) -> tuple[Path, dict]:
    publisher_meta = resolve_publisher(final_url, candidate.get("publisher_hints", []))
    document_id = stable_document_id(final_url)
    record = {
        "document_id": document_id,
        "document_type": "linked_source_pdf" if source_format == "pdf" else "linked_source_article",
        "source_format": source_format,
        "parent_topics": candidate.get("parent_topics", []),
        "title": title or candidate.get("title", ""),
        "publisher": publisher_meta["publisher"],
        "publisher_parent": publisher_meta["publisher_parent"],
        "source_url": final_url,
        "original_discovered_url": original_url,
        "source_domain": publisher_meta["source_domain"],
        "source_group": publisher_meta["source_group"],
        "language": "en",
        "categories": candidate.get("categories", []),
        "discovered_via": candidate.get("discovered_via", []),
        "trust_tier": candidate.get("trust_tier", "tier_1"),
        "trusted_domain": final_trust.matched_domain,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "reuse_status": "review_before_redistribution",
        "content_type": content_type,
        "text": text,
    }
    if page_count is not None:
        record["page_count"] = page_count

    output_dir = _output_dir_for_source(documents_root, publisher_meta["source_group"])
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{document_id}.json"
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    return path, record


def download_source_candidate(
    candidate: dict,
    documents_root: Path,
    timeout: tuple[int, int] | int = DEFAULT_TIMEOUT,
) -> DownloadResult:
    url = candidate.get("url", "")

    if not url:
        return DownloadResult("skipped", url, "missing_url")
    if is_obviously_spanish_url(url):
        return DownloadResult("skipped", url, "spanish_url")

    trust = evaluate_trusted_source(url)
    if not trust.allowed:
        return DownloadResult("skipped", url, trust.reason)

    try:
        response = requests.get(
            url,
            timeout=timeout,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.1",
            },
            allow_redirects=True,
        )
    except requests.RequestException as exc:
        return DownloadResult("failed", url, f"request_error:{type(exc).__name__}")

    final_url = response.url
    final_trust = evaluate_trusted_source(final_url)
    if not final_trust.allowed:
        return DownloadResult(
            "skipped",
            final_url,
            "redirected_to_untrusted_domain",
            http_status=response.status_code,
        )
    if is_obviously_spanish_url(final_url):
        return DownloadResult(
            "skipped",
            final_url,
            "redirected_to_spanish_url",
            http_status=response.status_code,
        )
    if response.status_code != 200:
        return DownloadResult("failed", final_url, "non_200_status", http_status=response.status_code)

    content_type = response.headers.get("Content-Type", "")
    declared = header_language(response.headers)
    if declared and is_spanish_language(declared):
        return DownloadResult(
            "skipped",
            final_url,
            "spanish_content_language",
            http_status=200,
            content_type=content_type,
        )

    if _is_pdf(content_type, final_url):
        try:
            pdf_title, text, page_count = extract_pdf_text(response.content)
        except Exception as exc:
            return DownloadResult(
                "failed",
                final_url,
                f"pdf_parse_error:{type(exc).__name__}",
                http_status=200,
                content_type=content_type,
                source_format="pdf",
            )
        if len(text.split()) < 80:
            return DownloadResult(
                "skipped",
                final_url,
                "insufficient_pdf_text",
                http_status=200,
                content_type=content_type,
                source_format="pdf",
            )

        path, record = _write_document(
            candidate=candidate,
            documents_root=documents_root,
            final_url=final_url,
            original_url=url,
            title=pdf_title or candidate.get("title", ""),
            text=text,
            source_format="pdf",
            content_type=content_type,
            final_trust=final_trust,
            page_count=page_count,
        )
        return DownloadResult(
            "downloaded",
            final_url,
            document_path=str(path),
            document_id=record["document_id"],
            publisher=record["publisher"],
            http_status=200,
            content_type=content_type,
            source_format="pdf",
        )

    if not _is_html(content_type, final_url):
        return DownloadResult(
            "skipped",
            final_url,
            "unsupported_content_type",
            http_status=200,
            content_type=content_type,
        )

    # Keep HTML as raw bytes. BeautifulSoup/lxml can honor the page's own
    # charset declaration, avoiding incorrect Requests decoding guesses.
    html_bytes = response.content
    if html_declares_spanish(html_bytes):
        return DownloadResult(
            "skipped",
            final_url,
            "spanish_html_lang",
            http_status=200,
            content_type=content_type,
            source_format="html",
        )

    extracted_title, text = extract_article_text(html_bytes)
    if len(text.split()) < 80:
        return DownloadResult(
            "skipped",
            final_url,
            "insufficient_article_text",
            http_status=200,
            content_type=content_type,
            source_format="html",
        )

    path, record = _write_document(
        candidate=candidate,
        documents_root=documents_root,
        final_url=final_url,
        original_url=url,
        title=extracted_title or candidate.get("title", ""),
        text=text,
        source_format="html",
        content_type=content_type,
        final_trust=final_trust,
    )
    return DownloadResult(
        "downloaded",
        final_url,
        document_path=str(path),
        document_id=record["document_id"],
        publisher=record["publisher"],
        http_status=200,
        content_type=content_type,
        source_format="html",
    )


def download_source_candidates(
    candidates: list[dict],
    documents_root: Path,
    delay_seconds: float = 0.5,
    progress_every: int = 10,
) -> list[DownloadResult]:
    results: list[DownloadResult] = []
    total = len(candidates)
    downloaded = skipped = failed = 0

    for index, candidate in enumerate(candidates, start=1):
        result = download_source_candidate(candidate, documents_root)
        results.append(result)

        if result.status == "downloaded":
            downloaded += 1
        elif result.status == "skipped":
            skipped += 1
        else:
            failed += 1

        if index == 1 or index == total or (progress_every > 0 and index % progress_every == 0):
            print(
                f"    [{index}/{total}] downloaded={downloaded} "
                f"skipped={skipped} failed={failed}"
            )

        if delay_seconds > 0 and index < total:
            time.sleep(delay_seconds)

    return results
