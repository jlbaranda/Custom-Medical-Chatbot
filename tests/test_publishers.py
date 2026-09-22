from ingestion.sources.web.publishers import resolve_publisher


def test_actual_publisher_uses_medlineplus_organization_hint():
    metadata = resolve_publisher(
        "https://www.niddk.nih.gov/health-information/diabetes",
        ["National Institute of Diabetes and Digestive and Kidney Diseases"],
    )
    assert metadata["publisher"] == "National Institute of Diabetes and Digestive and Kidney Diseases"
    assert metadata["publisher_parent"] == "National Institutes of Health"
    assert metadata["source_group"] == "nih"
