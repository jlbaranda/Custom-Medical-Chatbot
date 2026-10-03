from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path

from ..types import INTENTS, Intent

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
HELDOUT_PATH = Path(__file__).resolve().parents[1] / "eval" / "heldout.jsonl"


@dataclass(frozen=True)
class Example:
    text: str
    intent: Intent
    personal: int
    injection: int
    attack: str = ""


def read_jsonl(path: Path) -> list[Example]:
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            row = json.loads(line)
            out.append(Example(row["text"].strip(), Intent(row["intent"]), int(row.get("personal", 0)),
                               int(row.get("injection", 0)), row.get("attack", "")))
    return out


def load_training(data_dir: Path = DATA_DIR, exclude: tuple[str, ...] = ()) -> list[Example]:
    rows: list[Example] = []
    for path in sorted(data_dir.glob("train_*.jsonl")):
        if path.stem.removeprefix("train_") in exclude:
            continue
        rows.extend(read_jsonl(path))
    # Exact-duplicate removal; held-out texts are excluded so eval stays clean.
    heldout = {e.text.lower() for e in read_jsonl(HELDOUT_PATH)} if HELDOUT_PATH.exists() else set()
    seen, unique = set(), []
    for e in rows:
        key = e.text.lower()
        if key not in seen and key not in heldout:
            seen.add(key)
            unique.append(e)
    return unique


def stratified_split(rows: list[Example], val_fraction: float = 0.12, seed: int = 13):
    rng = random.Random(seed)
    train, val = [], []
    for intent in INTENTS:
        group = [e for e in rows if e.intent is intent]
        rng.shuffle(group)
        n_val = max(1, int(len(group) * val_fraction)) if group else 0
        val.extend(group[:n_val])
        train.extend(group[n_val:])
    rng.shuffle(train)
    return train, val
