from pathlib import Path

from ingestion.medlineplus.extract_medlineplus_topics import extract_selected_topics


def test_extract_selected_topic(tmp_path: Path):
    xml = """<?xml version="1.0"?>
<health-topics>
  <health-topic id="1" title="Diabetes" url="https://medlineplus.gov/diabetes.html" language="English">
    <full-summary><p>Diabetes summary.</p></full-summary>
    <primary-institute name="NIDDK" url="https://www.niddk.nih.gov/" />
    <related-topic title="Type 1 Diabetes" url="https://medlineplus.gov/diabetestype1.html" language="English" />
    <site title="Trusted" url="https://www.niddk.nih.gov/health-information/diabetes" language-mapped-url="https://www.niddk.nih.gov/espanol/diabetes">
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
    records = extract_selected_topics(path, ["Diabetes"])
    record = records[0]
    assert record["language"] == "en"
    assert len(record["resources"]) == 1
    assert record["resources"][0]["trusted_domain"] == "nih.gov"
    assert len(record["excluded_resources"]) == 1
    assert record["excluded_resources"][0]["reason"] == "domain_not_allowlisted"
