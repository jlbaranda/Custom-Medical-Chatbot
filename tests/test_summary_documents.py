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

def test_summary_html_is_converted_to_plain_text():
    topic = {
        "title": "Hypothyroidism",
        "url": "https://medlineplus.gov/hypothyroidism.html",
        "medlineplus_summary": {
            "text": """
                <h3>What are the symptoms of hypothyroidism?</h3>

                <p>
                    Symptoms may include
                    <a href="https://medlineplus.gov/fatigue.html">fatigue</a>.
                </p>

                <ul>
                    <li>Weight gain</li>
                    <li>A puffy face</li>
                </ul>
            """,
            "source_url": "https://medlineplus.gov/hypothyroidism.html",
        },
    }

    doc = build_summary_document(topic)

    assert doc is not None

    text = doc["text"]

    assert "<h3>" not in text
    assert "<p>" not in text
    assert "<li>" not in text
    assert "<a " not in text

    assert "What are the symptoms of hypothyroidism?" in text
    assert "Symptoms may include fatigue." in text
    assert "Weight gain" in text
    assert "A puffy face" in text