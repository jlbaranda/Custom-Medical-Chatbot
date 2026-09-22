from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from ingestion.cleaners.text_cleaner import clean_text


def _summary_document_id(topic_url: str, title: str) -> str:
    key = topic_url or title
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    return f"medlineplus_summary_{digest}"


def build_summary_document(topic_record: dict) -> dict | None:
    summary = topic_record.get("medlineplus_summary", {})
    text = clean_text(summary.get("text", ""))
    if not text:
        return None

    title = topic_record.get("title", "")
    source_url = summary.get("source_url") or topic_record.get("url", "")
    return {
        "document_id": _summary_document_id(source_url, title),
        "document_type": "medlineplus_topic_summary",
        "source_format": "html_summary",
        "parent_topics": [title],
        "title": f"{title} - MedlinePlus Summary",
        "publisher": "MedlinePlus / National Library of Medicine",
        "publisher_parent": "National Library of Medicine",
        "source_url": source_url,
        "source_domain": "medlineplus.gov",
        "source_group": "medlineplus",
        "language": "en",
        "categories": ["Topic Summary"],
        "discovered_via": {
            "provider": "MedlinePlus XML",
            "topic": title,
            "topic_url": topic_record.get("url", ""),
        },
        "trust_tier": "tier_1",
        "trusted_domain": "medlineplus.gov",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "reuse_status": "medlineplus_summary",
        "text": text,
    }


def write_summary_document(topic_record: dict, output_dir: Path) -> Path | None:
    document = build_summary_document(topic_record)
    if document is None:
        return None
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{document['document_id']}.json"
    path.write_text(json.dumps(document, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
