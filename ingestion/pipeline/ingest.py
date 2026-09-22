from __future__ import annotations

import argparse
import json
from pathlib import Path

from ingestion.chunking.chunker import chunk_text
from ingestion.discovery.medlineplus.parse_topics import (
    DEFAULT_XML_URL,
    download_xml,
    extract_selected_topics,
    load_selected_topics,
    write_outputs,
)
from ingestion.sources.medlineplus.summary_documents import write_summary_document
from ingestion.sources.web.html_downloader import download_source_candidates


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_documents(documents_root: Path) -> list[dict]:
    documents = []
    for path in sorted(documents_root.rglob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if record.get("document_id") and record.get("text"):
            documents.append(record)
    return documents


def build_corpus_manifest(documents: list[dict], chunks: list[dict]) -> dict:
    by_group: dict[str, int] = {}
    by_type: dict[str, int] = {}
    by_publisher: dict[str, int] = {}
    by_format: dict[str, int] = {}

    for document in documents:
        group = document.get("source_group", "unknown")
        doc_type = document.get("document_type", "unknown")
        publisher = document.get("publisher", "unknown")
        source_format = document.get("source_format", "unknown")
        by_group[group] = by_group.get(group, 0) + 1
        by_type[doc_type] = by_type.get(doc_type, 0) + 1
        by_publisher[publisher] = by_publisher.get(publisher, 0) + 1
        by_format[source_format] = by_format.get(source_format, 0) + 1

    return {
        "documents": len(documents),
        "chunks": len(chunks),
        "documents_by_source_group": dict(sorted(by_group.items())),
        "documents_by_type": dict(sorted(by_type.items())),
        "documents_by_publisher": dict(sorted(by_publisher.items())),
        "documents_by_format": dict(sorted(by_format.items())),
    }



def aggregate_source_candidates(topics: list[dict]) -> list[dict]:
    """Deduplicate linked pages while preserving every topic/provenance path.

    The same NIH/CDC article can be linked from more than one MedlinePlus topic.
    We download that URL once and keep all parent topics/discovery records.
    """
    by_url: dict[str, dict] = {}

    for topic in topics:
        for candidate in topic.get("source_candidates", []):
            url = candidate.get("url", "")
            if not url:
                continue

            if url not in by_url:
                merged = dict(candidate)
                merged["parent_topics"] = []
                merged["discovered_via"] = []
                by_url[url] = merged

            merged = by_url[url]
            topic_name = topic.get("title", "")
            if topic_name and topic_name not in merged["parent_topics"]:
                merged["parent_topics"].append(topic_name)

            provenance = candidate.get("discovered_via", {})
            if provenance and provenance not in merged["discovered_via"]:
                merged["discovered_via"].append(provenance)

            for hint in candidate.get("publisher_hints", []):
                if hint not in merged.setdefault("publisher_hints", []):
                    merged["publisher_hints"].append(hint)
            for category in candidate.get("categories", []):
                if category not in merged.setdefault("categories", []):
                    merged["categories"].append(category)

    return list(by_url.values())


def clean_generated_outputs(documents_root: Path, chunks_path: Path, logs_dir: Path) -> None:
    """Remove generated corpus artifacts while leaving source code/.gitkeep files intact."""
    if documents_root.exists():
        for path in documents_root.rglob("*.json"):
            path.unlink(missing_ok=True)
    chunks_path.unlink(missing_ok=True)
    if logs_dir.exists():
        for pattern in ("*.json", "*.jsonl"):
            for path in logs_dir.glob(pattern):
                path.unlink(missing_ok=True)


def run_pipeline(
    xml_url: str,
    xml_path: Path,
    selected_topics_path: Path,
    discovery_dir: Path,
    documents_root: Path,
    chunks_path: Path,
    logs_dir: Path,
    chunk_size_words: int,
    overlap_words: int,
    skip_downloads: bool = False,
    clean_generated: bool = False,
) -> None:
    if clean_generated:
        print("[0/6] Cleaning previously generated documents/chunks/logs...")
        clean_generated_outputs(documents_root, chunks_path, logs_dir)

    print("[1/6] Getting MedlinePlus XML discovery dataset...")
    download_xml(xml_url, xml_path)

    print("[2/6] Discovering selected topics and trusted English source candidates...")
    selected = load_selected_topics(selected_topics_path)
    topics = extract_selected_topics(xml_path, selected)
    write_outputs(topics, discovery_dir)

    print("[3/6] Creating MedlinePlus summary documents...")
    summary_paths = []
    for topic in topics:
        path = write_summary_document(topic, documents_root / "medlineplus")
        if path is not None:
            summary_paths.append(path)

    aggregated_candidates = aggregate_source_candidates(topics)
    download_log: list[dict] = []
    if skip_downloads:
        print("[4/6] Skipping linked-source downloads (--skip-downloads).")
    else:
        print("[4/6] Downloading deduplicated actual publisher pages discovered through MedlinePlus...")
        results = download_source_candidates(aggregated_candidates, documents_root)
        for candidate, result in zip(aggregated_candidates, results):
            download_log.append({
                "parent_topics": candidate.get("parent_topics", []),
                **result.to_dict(),
            })

    print("[5/6] Loading source documents and creating chunks...")
    all_documents = load_documents(documents_root)
    chunk_records: list[dict] = []

    for document in all_documents:
        for chunk in chunk_text(
            document.get("text", ""),
            document_id=document["document_id"],
            chunk_size_words=chunk_size_words,
            overlap_words=overlap_words,
        ):
            record = chunk.to_dict()
            record.update({
                "document_type": document.get("document_type", ""),
                "source_format": document.get("source_format", ""),
                "page_count": document.get("page_count"),
                "title": document.get("title", ""),
                "parent_topics": document.get("parent_topics", [document.get("parent_topic", "")] if document.get("parent_topic") else []),
                "publisher": document.get("publisher", ""),
                "publisher_parent": document.get("publisher_parent", ""),
                "source_url": document.get("source_url", ""),
                "source_domain": document.get("source_domain", ""),
                "source_group": document.get("source_group", ""),
                "language": document.get("language", "en"),
                "categories": document.get("categories", []),
                "discovered_via": document.get("discovered_via", {}),
                "trust_tier": document.get("trust_tier", "tier_1"),
                "trusted_domain": document.get("trusted_domain", ""),
            })
            chunk_records.append(record)

    write_jsonl(chunks_path, chunk_records)

    print("[6/6] Writing audit logs and corpus manifest...")
    logs_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(logs_dir / "source_downloads.jsonl", download_log)

    manifest = build_corpus_manifest(all_documents, chunk_records)
    (logs_dir / "corpus_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    summary = {
        "selected_topics": len(topics),
        "medlineplus_summary_documents": len(summary_paths),
        "source_candidates": sum(len(t.get("source_candidates", [])) for t in topics),
        "unique_source_candidates": len(aggregated_candidates),
        "download_attempts": len(download_log),
        "downloaded_external_documents": sum(r.get("status") == "downloaded" for r in download_log),
        "skipped_external_documents": sum(r.get("status") == "skipped" for r in download_log),
        "failed_external_documents": sum(r.get("status") == "failed" for r in download_log),
        "total_documents": len(all_documents),
        "chunks": len(chunk_records),
    }
    (logs_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print("Done.")
    print(json.dumps(summary, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the medical chatbot ingestion pipeline.")
    parser.add_argument("--xml-url", default=DEFAULT_XML_URL)
    parser.add_argument("--xml-path", default="data/raw/mplus_topics_2026-09-18.xml")
    parser.add_argument(
        "--selected-topics",
        default="ingestion/discovery/medlineplus/selected_topics.txt",
    )
    parser.add_argument("--discovery-dir", default="data/discovery/medlineplus")
    parser.add_argument("--documents-root", default="data/documents")
    parser.add_argument("--chunks-path", default="data/chunks/chunks.jsonl")
    parser.add_argument("--logs-dir", default="data/logs")
    parser.add_argument("--chunk-size-words", type=int, default=350)
    parser.add_argument("--overlap-words", type=int, default=60)
    parser.add_argument("--skip-downloads", action="store_true")
    parser.add_argument(
        "--clean-generated",
        action="store_true",
        help="Delete previously generated document JSON, chunks, and audit logs before rebuilding.",
    )
    args = parser.parse_args()

    run_pipeline(
        xml_url=args.xml_url,
        xml_path=Path(args.xml_path),
        selected_topics_path=Path(args.selected_topics),
        discovery_dir=Path(args.discovery_dir),
        documents_root=Path(args.documents_root),
        chunks_path=Path(args.chunks_path),
        logs_dir=Path(args.logs_dir),
        chunk_size_words=args.chunk_size_words,
        overlap_words=args.overlap_words,
        skip_downloads=args.skip_downloads,
        clean_generated=args.clean_generated,
    )


if __name__ == "__main__":
    main()
