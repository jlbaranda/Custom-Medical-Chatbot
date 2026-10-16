import sys
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1])
)

from retrieval.pubmedbert import build_index


if __name__ == "__main__":
    build_index()