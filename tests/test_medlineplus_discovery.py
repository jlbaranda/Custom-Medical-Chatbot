from pathlib import Path

from ingestion.discovery.medlineplus.parse_topics import extract_selected_topics


def test_medlineplus_is_discovery_layer(tmp_path: Path):
    xml = """<?xml version="1.0"?>
<health-topics>
  <health-topic id="1" title="Diabetes" url="https://medlineplus.gov/diabetes.html" language="English">
    <full-summary><p>Diabetes summary.</p></full-summary>
    <primary-institute name="NIDDK" url="https://www.niddk.nih.gov/" />
    <related-topic title="Type 1 Diabetes" url="https://medlineplus.gov/diabetestype1.html" language="English" />
    <site title="NIDDK Diabetes" url="https://www.niddk.nih.gov/health-information/diabetes" language-mapped-url="https://www.niddk.nih.gov/espanol/diabetes">
      <organization name="NIDDK" />
      <information-category name="Start Here" />
    </site>
    <site title="Not allowlisted" url="https://example.org/article">
      <organization name="Example" />
    </site>
  </health-topic>
</health-topics>
"""
    path = tmp_path / "topics.xml"
    path.write_text(xml, encoding="utf-8")

    record = extract_selected_topics(path, ["Diabetes"])[0]
    assert record["medlineplus_summary"]["text"] == "Diabetes summary."
    assert len(record["source_candidates"]) == 1
    candidate = record["source_candidates"][0]
    assert candidate["publisher_hints"] == ["NIDDK"]
    assert candidate["discovered_via"]["provider"] == "MedlinePlus"
    assert candidate["source_group"] == "nih"
    assert len(record["excluded_candidates"]) == 1
    assert record["excluded_candidates"][0]["reason"] == "domain_not_allowlisted"
