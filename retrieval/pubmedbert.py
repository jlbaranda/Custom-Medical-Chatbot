from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import ollama

from guardrails.types import Passage


ROOT = Path(__file__).resolve().parents[1]

CHUNKS_PATH = ROOT / "data" / "chunks" / "chunks.jsonl"
INDEX_DIR = ROOT / "data" / "index" / "pubmedbert"

EMBEDDING_MODEL = (
    "hf.co/cmiralop/"
    "BiomedNLP-PubMedBERT-Base-Uncased-Abstract-Fulltext-109M:F16"
)


def normalize_vectors(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(
        vectors,
        axis=1,
        keepdims=True,
    )

    norms = np.clip(norms, 1e-12, None)

    return vectors / norms


def build_index(batch_size: int = 16) -> None:
    chunks = []

    with CHUNKS_PATH.open(
            "r",
            encoding="utf-8",
    ) as file:
        for line in file:
            if line.strip():
                chunks.append(json.loads(line))

    print(f"Loaded {len(chunks)} chunks.")

    vectors = []

    for start in range(0, len(chunks), batch_size):
        batch = chunks[
            start:start + batch_size
        ]

        texts = [
            chunk["text"]
            for chunk in batch
        ]

        response = ollama.embed(
            model=EMBEDDING_MODEL,
            input=texts,
        )

        vectors.extend(
            response["embeddings"]
        )

        finished = min(
            start + batch_size,
            len(chunks),
            )

        print(
            f"Embedded {finished}/{len(chunks)}"
        )

    matrix = np.asarray(
        vectors,
        dtype=np.float32,
    )

    matrix = normalize_vectors(matrix)

    print("Embedding shape:", matrix.shape)

    INDEX_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    np.save(
        INDEX_DIR / "embeddings.npy",
        matrix,
        )

    with (
            INDEX_DIR / "metadata.jsonl"
    ).open(
        "w",
        encoding="utf-8",
    ) as file:

        for chunk in chunks:
            file.write(
                json.dumps(
                    chunk,
                    ensure_ascii=False,
                )
                + "\n"
            )

class PubMedBERTRetriever:
    def __init__(self):
        self.embeddings = np.load(
            INDEX_DIR / "embeddings.npy"
        )

        self.chunks = []

        with (
                INDEX_DIR / "metadata.jsonl"
        ).open(
            "r",
            encoding="utf-8",
        ) as file:
            for line in file:
                if line.strip():
                    self.chunks.append(
                        json.loads(line)
                    )

        if len(self.chunks) != len(self.embeddings):
            raise ValueError(
                "Chunk metadata and embeddings do not match."
            )

    def search(
            self,
            query: str,
            k: int,
    ) -> list[Passage]:

        response = ollama.embed(
            model=EMBEDDING_MODEL,
            input=query,
        )

        query_vector = np.asarray(
            response["embeddings"][0],
            dtype=np.float32,
        )

        query_vector /= max(
            np.linalg.norm(query_vector),
            1e-12,
        )

        # Embeddings are normalized, so dot product
        # equals cosine similarity.
        scores = self.embeddings @ query_vector

        indices = np.argsort(scores)[::-1][:k]

        results = []

        for index in indices:
            chunk = self.chunks[index]

            results.append(
                Passage(
                    chunk_id=chunk["chunk_id"],
                    text=chunk["text"],
                    title=chunk.get("title", ""),
                    publisher=chunk.get(
                        "publisher",
                        "",
                    ),
                    source_url=chunk.get(
                        "source_url",
                        "",
                    ),
                    score=float(scores[index]),
                )
            )

        return results