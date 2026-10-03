"""Run the full comparison: train every model variant, eval each on the held-out set,
write one summary table. Models that already exist are not retrained.

    python -m guardrails.eval.experiments               # everything
    python -m guardrails.eval.experiments --eval-only   # just re-score existing models
    python -m guardrails.eval.experiments --low-memory  # gradient checkpointing, batch 8

Variants (backbone x training data) answer two paper questions:
  1. Does a fine-tuned encoder beat a TF-IDF baseline, and does the backbone matter
     (ModernBERT: web text vs BiomedBERT: PubMed abstracts)?
  2. Does adversarial training data reduce jailbreak under-refusal?
"""
from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = Path(__file__).with_name("results")
BIOMEDBERT = "microsoft/BiomedNLP-BiomedBERT-base-uncased-abstract-fulltext"

# (model path relative to ROOT, train args)
VARIANTS: list[tuple[str, list[str]]] = [
    ("models/guardrail-tfidf-v1.pkl", ["--backend", "tfidf", "--exclude", "adversarial"]),
    ("models/guardrail-tfidf-v2.pkl", ["--backend", "tfidf"]),
    ("models/guardrail-modernbert-v1", ["--exclude", "adversarial"]),
    ("models/guardrail-modernbert-v2", []),
    ("models/guardrail-biomedbert-v2", ["--backbone", BIOMEDBERT]),
]


def run(args: list[str]) -> None:
    print(">", " ".join(args), flush=True)
    subprocess.run([sys.executable, "-m", *args], cwd=ROOT, check=True)


def summary_row(model_path: str) -> dict | None:
    stem = Path(model_path).stem if model_path.endswith(".pkl") else Path(model_path).name
    prefix = "tfidf-" if model_path.endswith(".pkl") else "multihead-"
    md = RESULTS / f"{prefix}{stem}.md"
    if not md.exists():
        return None
    row = {"model": stem}
    for line in md.read_text(encoding="utf-8").splitlines():
        parts = [p.strip() for p in line.strip("|").split("|")]
        if len(parts) == 2 and parts[0] in ("under_refusal", "over_refusal", "emergency_recall", "refusal_rate_harmful"):
            row[parts[0]] = parts[1]
        if line.startswith("Held-out set"):
            row["latency"] = line.split("latency ")[-1].split(" ms")[0] + " ms"
    return row


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval-only", action="store_true")
    ap.add_argument("--low-memory", action="store_true")
    args = ap.parse_args()

    for model_path, train_args in VARIANTS:
        is_tfidf = model_path.endswith(".pkl")
        if not args.eval_only and not (ROOT / model_path).exists():
            extra = ["--low-memory", "--batch-size", "8"] if args.low_memory and not is_tfidf else []
            run(["guardrails.train", *train_args, "--out", model_path, *extra])
        if (ROOT / model_path).exists():
            run(["guardrails.eval.run_eval", "--model", model_path])

    rows = [r for r in (summary_row(m) for m, _ in VARIANTS) if r]
    if not rows:
        return
    fields = ["model", "under_refusal", "over_refusal", "emergency_recall", "refusal_rate_harmful", "latency"]
    with open(RESULTS / "summary.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    lines = ["# Guardrail classifier comparison (held-out red-team set)", "",
             "| " + " | ".join(fields) + " |", "|" + "---|" * len(fields)]
    lines += ["| " + " | ".join(r.get(f, "") for f in fields) + " |" for r in rows]
    (RESULTS / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
