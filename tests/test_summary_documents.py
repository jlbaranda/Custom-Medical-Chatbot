from ingestion.sources.medlineplus.summary_documents import build_summary_document


def test_summary_becomes_its_own_medlineplus_document():
    topic = {
        "title": "Diabetes",
        "url": "https://medlineplus.gov/diabetes.html",
        "medlineplus_summary": {
            "text": "A patient-friendly summary.",
            "source_url": "https://medlineplus.gov/diabetes.html",
        },
    }
    doc = build_summary_document(topic)
    assert doc is not None
    assert doc["document_type"] == "medlineplus_topic_summary"
    assert doc["publisher"] == "MedlinePlus / National Library of Medicine"
    assert doc["source_url"] == "https://medlineplus.gov/diabetes.html"
