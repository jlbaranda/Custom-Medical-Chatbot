from ingestion.pipeline.ingest import clean_generated_outputs


def test_clean_generated_outputs_removes_generated_files(tmp_path):
    docs = tmp_path / "documents"
    (docs / "nih").mkdir(parents=True)
    (docs / "nih" / "doc.json").write_text("{}", encoding="utf-8")
    (docs / "nih" / ".gitkeep").write_text("", encoding="utf-8")

    chunks = tmp_path / "chunks" / "chunks.jsonl"
    chunks.parent.mkdir(parents=True)
    chunks.write_text("{}\n", encoding="utf-8")

    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "summary.json").write_text("{}", encoding="utf-8")
    (logs / "source_downloads.jsonl").write_text("{}\n", encoding="utf-8")
    (logs / ".gitkeep").write_text("", encoding="utf-8")

    clean_generated_outputs(docs, chunks, logs)

    assert not (docs / "nih" / "doc.json").exists()
    assert (docs / "nih" / ".gitkeep").exists()
    assert not chunks.exists()
    assert not (logs / "summary.json").exists()
    assert not (logs / "source_downloads.jsonl").exists()
    assert (logs / ".gitkeep").exists()
