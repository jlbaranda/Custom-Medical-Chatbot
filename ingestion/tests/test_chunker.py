from ingestion.chunking.chunker import chunk_text


def test_chunking_with_overlap():
    text = " ".join(f"word{i}" for i in range(100))
    chunks = chunk_text(text, "doc1", chunk_size_words=30, overlap_words=5)
    assert len(chunks) == 4
    assert chunks[0].word_count == 30
    assert chunks[1].text.split()[0] == "word25"
    assert chunks[-1].chunk_id == "doc1:chunk:3"


def test_invalid_overlap():
    try:
        chunk_text("hello world", "doc", chunk_size_words=10, overlap_words=10)
    except ValueError:
        return
    raise AssertionError("Expected ValueError")
