from __future__ import annotations

from dataclasses import dataclass, asdict


DEFAULT_MIN_CHUNK_WORDS = 80


@dataclass
class Chunk:
    chunk_id: str
    document_id: str
    index: int
    text: str
    word_count: int

    def to_dict(self) -> dict:
        return asdict(self)


def _word_stream_with_blocks(text: str) -> list[tuple[str, int]]:
    """Flatten text to words while remembering paragraph/heading boundaries."""
    stream: list[tuple[str, int]] = []
    block_index = 0
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        words = line.split()
        if not words:
            continue
        stream.extend((word, block_index) for word in words)
        block_index += 1
    return stream


def _render_window(window: list[tuple[str, int]]) -> str:
    if not window:
        return ""
    parts: list[str] = []
    last_block: int | None = None
    current: list[str] = []
    for word, block in window:
        if last_block is None or block == last_block:
            current.append(word)
        else:
            parts.append(" ".join(current))
            current = [word]
        last_block = block
    if current:
        parts.append(" ".join(current))
    return "\n\n".join(parts)


def _merge_tiny_trailing_window(
    windows: list[list[tuple[str, int]]],
    overlap_words: int,
    min_chunk_words: int,
) -> None:
    """Avoid a tiny final chunk while preserving any non-overlapping tail words.

    Sliding windows can create a final chunk that is almost entirely (or entirely)
    overlap with the previous chunk. If that final window is below the configured
    minimum size, remove it. Any words beyond the normal overlap are appended to
    the previous window so no source text is lost.
    """
    if len(windows) < 2 or min_chunk_words <= 0:
        return

    trailing = windows[-1]
    if len(trailing) >= min_chunk_words:
        return

    # The start of the trailing window overlaps the previous window. Only append
    # the portion beyond that overlap; otherwise we would duplicate text inside
    # the merged chunk.
    overlap_in_trailing = min(overlap_words, len(trailing))
    unique_tail = trailing[overlap_in_trailing:]
    if unique_tail:
        windows[-2].extend(unique_tail)

    windows.pop()


def chunk_text(
    text: str,
    document_id: str,
    chunk_size_words: int = 350,
    overlap_words: int = 60,
    min_chunk_words: int | None = None,
) -> list[Chunk]:
    if chunk_size_words <= 0:
        raise ValueError("chunk_size_words must be > 0")
    if overlap_words < 0:
        raise ValueError("overlap_words must be >= 0")
    if overlap_words >= chunk_size_words:
        raise ValueError("overlap_words must be smaller than chunk_size_words")
    if min_chunk_words is None:
        # Keep the production default at 80 words for the normal 350-word
        # chunks, but scale down automatically for deliberately small chunk
        # sizes used in tests/experiments so existing behavior is preserved.
        effective_min_chunk_words = min(
            DEFAULT_MIN_CHUNK_WORDS,
            max(1, chunk_size_words // 4),
        )
    else:
        if min_chunk_words < 0:
            raise ValueError("min_chunk_words must be >= 0")
        if min_chunk_words > chunk_size_words:
            raise ValueError("min_chunk_words must be <= chunk_size_words")
        effective_min_chunk_words = min_chunk_words

    stream = _word_stream_with_blocks(text)
    if not stream:
        return []

    step = chunk_size_words - overlap_words
    windows: list[list[tuple[str, int]]] = []
    start = 0

    while start < len(stream):
        window = stream[start:start + chunk_size_words]
        if not window:
            break
        windows.append(window)
        start += step

    _merge_tiny_trailing_window(
        windows,
        overlap_words=overlap_words,
        min_chunk_words=effective_min_chunk_words,
    )

    chunks: list[Chunk] = []
    for index, window in enumerate(windows):
        chunks.append(
            Chunk(
                chunk_id=f"{document_id}:chunk:{index}",
                document_id=document_id,
                index=index,
                text=_render_window(window),
                word_count=len(window),
            )
        )

    return chunks
