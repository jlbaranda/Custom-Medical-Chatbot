from __future__ import annotations

import argparse
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable

from ingestion.common.language_filters import is_english_language, is_obviously_spanish_url
from ingestion.common.source_policy import evaluate_trusted_source

DEFAULT_XML_URL = "https://medlineplus.gov/xml/mplus_topics_2026-09-18.xml"


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")


def load_selected_topics(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def download_xml(url: str, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_size > 0:
        return destination

    req = urllib.request.Request(url, headers={"User-Agent": "medical-chatbot-ingestion/2.0"})
    with urllib.request.urlopen(req, timeout=120) as response, destination.open("wb") as out:
        while True:
            block = response.read(1024 * 1024)
            if not block:
                break
            out.write(block)
    return destination


def _text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return "".join(element.itertext()).strip()


def _html(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return "".join(ET.tostring(child, encoding="unicode") for child in list(element)).strip()


def _children_text(topic: ET.Element, tag: str) -> list[str]:
    values = []
    for node in topic.findall(tag):
        value = _text(node)
        if value:
            values.append(value)
    return values


def _find_topic_title(topic: ET.Element) -> str:
    return (topic.get("title") or _text(topic.find("title"))).strip()


def _extract_related_topics(topic: ET.Element) -> list[dict]:
    result = []
    for node in topic.findall("related-topic"):
        title = (node.get("title") or _text(node)).strip()
        url = (node.get("url") or "").strip()
        if not title:
            continue
        language = (node.get("language") or "en").strip()
        if not is_english_language(language):
            continue
        if url and is_obviously_spanish_url(url):
            continue
        result.append({"title": title, "url": url, "language": "en"})
    return result


def _extract_primary_institute(topic: ET.Element) -> dict | None:
    node = topic.find("primary-institute")
    if node is None:
        return None
    name = (node.get("name") or _text(node)).strip()
    url = (node.get("url") or "").strip()
    if not name and not url:
        return None
    return {"name": name, "url": url}


def _extract_source_candidates(topic: ET.Element, topic_title: str, topic_url: str) -> tuple[list[dict], list[dict]]:
    candidates: list[dict] = []
    excluded: list[dict] = []

    for site in topic.findall("site"):
        title = (site.get("title") or _text(site.find("title"))).strip()
        url = (site.get("url") or "").strip()
        organizations = [
            (node.get("name") or _text(node)).strip()
            for node in site.findall("organization")
            if (node.get("name") or _text(node)).strip()
        ]
        categories = [
            (node.get("name") or _text(node)).strip()
            for node in site.findall("information-category")
            if (node.get("name") or _text(node)).strip()
        ]
        descriptions = [_text(node) for node in site.findall("standard-description") if _text(node)]

        base = {
            "title": title,
            "url": url,
            "language": "en",
            "publisher_hints": organizations,
            "categories": categories,
            "standard_descriptions": descriptions,
            "discovered_via": {
                "provider": "MedlinePlus",
                "topic": topic_title,
                "topic_url": topic_url,
            },
        }

        # MedlinePlus often includes a language-mapped-url pointing to the
        # Spanish version of the same resource. Version 1 intentionally omits it.
        if not url:
            excluded.append({**base, "reason": "missing_url"})
            continue
        if is_obviously_spanish_url(url):
            excluded.append({**base, "reason": "spanish_url"})
            continue

        trust = evaluate_trusted_source(url)
        if not trust.allowed:
            excluded.append({**base, "reason": trust.reason})
            continue

        candidates.append({
            **base,
            "trust_tier": "tier_1",
            "trust_reason": trust.reason,
            "trusted_domain": trust.matched_domain,
            "publisher_parent": trust.publisher_parent,
            "source_group": trust.source_group,
            "ingestion_status": "not_ingested",
        })

    return candidates, excluded


def extract_topic(topic: ET.Element) -> dict:
    title = _find_topic_title(topic)
    topic_url = (topic.get("url") or "").strip()
    candidates, excluded_candidates = _extract_source_candidates(topic, title, topic_url)
    summary_node = topic.find("full-summary")

    return {
        "discovery_id": topic.get("id") or slugify(title),
        "title": title,
        "url": topic_url,
        "language": "en",
        "date_created": topic.get("date-created") or "",
        "meta_description": topic.get("meta-desc") or "",
        "medlineplus_summary": {
            "text": _text(summary_node),
            "html": _html(summary_node),
            "publisher": "MedlinePlus / National Library of Medicine",
            "source_url": topic_url,
        },
        "also_called": _children_text(topic, "also-called"),
        "groups": [
            {"name": (node.get("name") or _text(node)).strip(), "url": (node.get("url") or "").strip()}
            for node in topic.findall("group")
        ],
        "mesh_headings": [
            {"descriptor": (node.get("descriptor") or _text(node)).strip(), "id": node.get("id") or ""}
            for node in topic.findall("mesh-heading")
        ],
        "related_topics": _extract_related_topics(topic),
        "primary_institute": _extract_primary_institute(topic),
        "source_candidates": candidates,
        "excluded_candidates": excluded_candidates,
        "candidate_filter_stats": {
            "total": len(candidates) + len(excluded_candidates),
            "kept_trusted_english": len(candidates),
            "skipped_spanish_url": sum(r.get("reason") == "spanish_url" for r in excluded_candidates),
            "skipped_domain_not_allowlisted": sum(
                r.get("reason") == "domain_not_allowlisted" for r in excluded_candidates
            ),
            "skipped_other": sum(
                r.get("reason") not in {"spanish_url", "domain_not_allowlisted"}
                for r in excluded_candidates
            ),
        },
    }


def extract_selected_topics(xml_path: Path, selected_titles: Iterable[str]) -> list[dict]:
    wanted = {title.casefold(): title for title in selected_titles}
    found: dict[str, dict] = {}

    for _, elem in ET.iterparse(xml_path, events=("end",)):
        if elem.tag != "health-topic":
            continue

        language = elem.get("language") or "English"
        if not is_english_language(language):
            elem.clear()
            continue

        title = _find_topic_title(elem)
        key = title.casefold()
        if key in wanted:
            found[key] = extract_topic(elem)
        elem.clear()

        if len(found) == len(wanted):
            break

    missing = [original for key, original in wanted.items() if key not in found]
    if missing:
        raise ValueError("Could not find selected topics: " + ", ".join(missing))

    return [found[title.casefold()] for title in selected_titles]


def write_outputs(records: list[dict], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    index = []

    for record in records:
        filename = slugify(record["title"]) + ".json"
        (output_dir / filename).write_text(
            json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        index.append({
            "title": record["title"],
            "file": filename,
            "url": record["url"],
            "source_candidate_count": len(record["source_candidates"]),
        })

    (output_dir / "index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    with (output_dir / "topics.jsonl").open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Use MedlinePlus as a discovery index for selected English medical topics."
    )
    parser.add_argument("--xml-url", default=DEFAULT_XML_URL)
    parser.add_argument("--xml-path", default="data/raw/mplus_topics_2026-09-18.xml")
    parser.add_argument(
        "--selected-topics",
        default="ingestion/discovery/medlineplus/selected_topics.txt",
    )
    parser.add_argument("--output-dir", default="data/discovery/medlineplus")
    args = parser.parse_args()

    xml_path = Path(args.xml_path)
    download_xml(args.xml_url, xml_path)
    selected = load_selected_topics(Path(args.selected_topics))
    records = extract_selected_topics(xml_path, selected)
    write_outputs(records, Path(args.output_dir))

    print(f"Discovered {len(records)} topics into {args.output_dir}")
    for record in records:
        stats = record["candidate_filter_stats"]
        print(
            f"- {record['title']}: {stats['kept_trusted_english']} trusted English source candidates "
            f"({stats['total']} total linked resources)"
        )


if __name__ == "__main__":
    main()
