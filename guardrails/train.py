"""Train the layer-2 request classifier.

    python -m guardrails.train                       # ModernBERT (default backbone)
    python -m guardrails.train --backbone microsoft/BiomedNLP-BiomedBERT-base-uncased-abstract-fulltext --out models/guardrail-biomedbert
    python -m guardrails.train --backend tfidf       # baseline
"""
from __future__ import annotations

import argparse
import json
import math
import random
import time
from pathlib import Path

from .classifier.data import Example, load_training, stratified_split
from .types import INTENTS, Intent

ROOT = Path(__file__).resolve().parents[1]


def metrics(rows: list[Example], preds) -> dict:
    n = len(rows)
    correct = sum(p.top_intent is e.intent for e, p in zip(rows, preds))
    f1s = {}
    for intent in INTENTS:
        tp = sum(p.top_intent is intent and e.intent is intent for e, p in zip(rows, preds))
        fp = sum(p.top_intent is intent and e.intent is not intent for e, p in zip(rows, preds))
        fn = sum(p.top_intent is not intent and e.intent is intent for e, p in zip(rows, preds))
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1s[intent.value] = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    present = [i.value for i in INTENTS if any(e.intent is i for e in rows)]
    return {
        "n": n,
        "intent_acc": correct / n,
        "intent_macro_f1": sum(f1s[i] for i in present) / len(present),
        "intent_f1": f1s,
        "personal_acc": sum((p.personal >= 0.5) == bool(e.personal) for e, p in zip(rows, preds)) / n,
        "injection_acc": sum((p.injection >= 0.5) == bool(e.injection) for e, p in zip(rows, preds)) / n,
    }


def train_tfidf(rows: list[Example], out: Path) -> dict:
    from .classifier.tfidf import TfidfClassifier

    train, val = stratified_split(rows)
    clf = TfidfClassifier.train(train)
    m = metrics(val, [clf.classify(e.text) for e in val])
    TfidfClassifier.train(rows).save(out)  # final model uses all training data
    return m


def train_transformer(rows: list[Example], out: Path, backbone: str, epochs: int, lr: float,
                      batch_size: int, seed: int, log, low_memory: bool = False) -> dict:
    import torch
    from torch import nn
    from transformers import AutoTokenizer, get_linear_schedule_with_warmup

    from .classifier.transformer import MAX_LEN, MultiHeadClassifier, TransformerClassifier
    from .normalize import normalize

    torch.manual_seed(seed)
    random.seed(seed)
    train, val = stratified_split(rows, seed=seed)
    tokenizer = AutoTokenizer.from_pretrained(backbone)
    model = MultiHeadClassifier(backbone)
    if low_memory:
        # Recompute activations in the backward pass instead of storing them: less RAM, ~30% slower.
        model.backbone.gradient_checkpointing_enable()

    intent_index = {i: k for k, i in enumerate(INTENTS)}
    counts = [max(1, sum(e.intent is i for e in train)) for i in INTENTS]
    weights = torch.tensor([len(train) / (len(INTENTS) * c) for c in counts], dtype=torch.float)
    ce = nn.CrossEntropyLoss(weight=weights)
    bce = nn.BCEWithLogitsLoss()

    def batches(data, shuffle):
        order = list(range(len(data)))
        if shuffle:
            random.shuffle(order)
        for s in range(0, len(order), batch_size):
            chunk = [data[k] for k in order[s:s + batch_size]]
            enc = tokenizer([normalize(e.text) for e in chunk], padding=True, truncation=True,
                            max_length=MAX_LEN, return_tensors="pt")
            yield (enc, torch.tensor([intent_index[e.intent] for e in chunk]),
                   torch.tensor([float(e.personal) for e in chunk]), torch.tensor([float(e.injection) for e in chunk]))

    optim = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.01)
    steps = epochs * math.ceil(len(train) / batch_size)
    sched = get_linear_schedule_with_warmup(optim, int(0.1 * steps), steps)

    best, best_state = None, None
    for epoch in range(epochs):
        model.train()
        t0, total = time.time(), 0.0
        for step, (enc, yi, yp, yj) in enumerate(batches(train, shuffle=True)):
            li, lp, lj = model(enc["input_ids"], enc["attention_mask"])
            loss = ce(li, yi) + 0.5 * bce(lp, yp) + 0.5 * bce(lj, yj)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optim.step()
            sched.step()
            optim.zero_grad()
            total += loss.item()
            if step % 20 == 0:
                log(f"epoch {epoch + 1} step {step} loss {loss.item():.3f}")
        clf = TransformerClassifier(model, tokenizer, name=f"multihead:{out.name}")
        preds = [p for s in range(0, len(val), 32) for p in clf.classify_batch([e.text for e in val[s:s + 32]])]
        m = metrics(val, preds)
        log(f"epoch {epoch + 1} done in {time.time() - t0:.0f}s train_loss {total / max(1, step + 1):.3f} "
            f"val acc {m['intent_acc']:.3f} macroF1 {m['intent_macro_f1']:.3f}")
        if best is None or m["intent_macro_f1"] >= best["intent_macro_f1"]:
            best = m
            best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}

    model.load_state_dict(best_state)
    clf = TransformerClassifier(model, tokenizer, name=f"multihead:{out.name}")
    clf.temperature = fit_temperature(clf, val, intent_index)
    log(f"temperature {clf.temperature:.2f}")
    clf.save(out, backbone, best)
    return best


def fit_temperature(clf, val: list[Example], intent_index: dict[Intent, int]) -> float:
    """Grid-search the softmax temperature that minimises validation NLL."""
    import torch

    from .normalize import normalize

    with torch.inference_mode():
        enc = clf.tokenizer([normalize(e.text) for e in val], padding=True, truncation=True,
                            max_length=128, return_tensors="pt")
        logits = clf.model(enc["input_ids"], enc["attention_mask"])[0]
    y = torch.tensor([intent_index[e.intent] for e in val])
    best_t, best_nll = 1.0, float("inf")
    for t in [0.5 + 0.1 * k for k in range(36)]:
        nll = torch.nn.functional.cross_entropy(logits / t, y).item()
        if nll < best_nll:
            best_t, best_nll = t, nll
    return best_t


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=["transformer", "tfidf"], default="transformer")
    ap.add_argument("--backbone", default="answerdotai/ModernBERT-base")
    ap.add_argument("--out", default=None)
    ap.add_argument("--epochs", type=int, default=4)
    ap.add_argument("--lr", type=float, default=5e-5)
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--seed", type=int, default=13)
    ap.add_argument("--low-memory", action="store_true", help="gradient checkpointing; use with --batch-size 8")
    ap.add_argument("--exclude", nargs="*", default=[], help="training files to leave out, e.g. adversarial (ablation)")
    args = ap.parse_args()

    rows = load_training(exclude=tuple(args.exclude))
    log_path = ROOT / "data" / "logs" / "guardrail_train.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    def log(msg: str) -> None:
        line = f"{time.strftime('%H:%M:%S')} {msg}"
        print(line, flush=True)
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    log(f"{len(rows)} training examples: " + ", ".join(f"{i.value}={sum(e.intent is i for e in rows)}" for i in INTENTS))
    if args.backend == "tfidf":
        out = ROOT / (args.out or "models/guardrail-tfidf.pkl")
        m = train_tfidf(rows, out)
    else:
        out = ROOT / (args.out or "models/guardrail-classifier")
        m = train_transformer(rows, out, args.backbone, args.epochs, args.lr, args.batch_size, args.seed, log,
                              low_memory=args.low_memory)
    log(f"saved {out}\n" + json.dumps(m, indent=2))


if __name__ == "__main__":
    main()
