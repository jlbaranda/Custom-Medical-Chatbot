from ingestion.pipeline.ingest import build_corpus_manifest


def test_manifest_separates_summary_and_external_sources():
    docs = [
        {
            "document_type": "medlineplus_topic_summary",
            "source_group": "medlineplus",
            "publisher": "MedlinePlus / National Library of Medicine",
            "source_format": "html_summary",
        },
        {
            "document_type": "linked_source_article",
            "source_group": "nih",
            "publisher": "NIDDK",
            "source_format": "html",
        },
    ]
    manifest = build_corpus_manifest(docs, [{}, {}, {}])
    assert manifest["documents"] == 2
    assert manifest["chunks"] == 3
    assert manifest["documents_by_source_group"]["nih"] == 1
    assert manifest["documents_by_type"]["medlineplus_topic_summary"] == 1
    assert manifest["documents_by_format"]["html"] == 1
    assert manifest["documents_by_format"]["html_summary"] == 1
