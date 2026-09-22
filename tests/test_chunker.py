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


def test_chunker_preserves_block_boundaries():
    text = "Heading\nParagraph one has useful information.\nParagraph two has more information."
    chunks = chunk_text(text, "doc", chunk_size_words=50, overlap_words=5)
    assert len(chunks) == 1
    assert "Heading\n\nParagraph one" in chunks[0].text
    assert "information.\n\nParagraph two" in chunks[0].text


def test_tiny_trailing_chunk_is_removed_when_fully_overlapped():
    # With size=350 and overlap=60, starts are 0, 290, 580. A 582-word
    # document would otherwise create a useless 2-word final overlap chunk.
    text = " ".join(f"word{i}" for i in range(582))
    chunks = chunk_text(text, "doc", chunk_size_words=350, overlap_words=60)

    assert len(chunks) == 2
    assert chunks[0].word_count == 350
    assert chunks[1].word_count == 292
    assert chunks[1].text.split()[-1] == "word581"


def test_small_trailing_chunk_merges_only_unique_tail_words():
    # Final window has 70 words: 60 overlap + 10 genuinely new words.
    # Those 10 words should extend the previous chunk instead of becoming a
    # separate undersized chunk.
    text = " ".join(f"word{i}" for i in range(650))
    chunks = chunk_text(text, "doc", chunk_size_words=350, overlap_words=60)

    assert len(chunks) == 2
    assert chunks[0].word_count == 350
    assert chunks[1].word_count == 360
    assert chunks[1].text.split()[-1] == "word649"


def test_short_document_is_kept_even_below_minimum_chunk_size():
    text = " ".join(f"word{i}" for i in range(25))
    chunks = chunk_text(text, "doc", chunk_size_words=350, overlap_words=60)

    assert len(chunks) == 1
    assert chunks[0].word_count == 25
