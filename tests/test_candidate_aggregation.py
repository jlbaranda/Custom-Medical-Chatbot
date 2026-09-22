from ingestion.pipeline.ingest import aggregate_source_candidates


def test_duplicate_source_url_keeps_all_parent_topics():
    topics = [
        {
            "title": "Diabetes",
            "source_candidates": [
                {
                    "url": "https://www.niddk.nih.gov/shared",
                    "publisher_hints": ["NIDDK"],
                    "categories": ["Start Here"],
                    "discovered_via": {"provider": "MedlinePlus", "topic": "Diabetes"},
                }
            ],
        },
        {
            "title": "High Blood Pressure",
            "source_candidates": [
                {
                    "url": "https://www.niddk.nih.gov/shared",
                    "publisher_hints": ["NIDDK"],
                    "categories": ["Related Issues"],
                    "discovered_via": {"provider": "MedlinePlus", "topic": "High Blood Pressure"},
                }
            ],
        },
    ]

    merged = aggregate_source_candidates(topics)
    assert len(merged) == 1
    assert merged[0]["parent_topics"] == ["Diabetes", "High Blood Pressure"]
    assert len(merged[0]["discovered_via"]) == 2
    assert set(merged[0]["categories"]) == {"Start Here", "Related Issues"}
