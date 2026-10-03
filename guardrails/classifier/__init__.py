from __future__ import annotations

import warnings
from pathlib import Path
from typing import Protocol

from ..types import Classification


class RequestClassifier(Protocol):
    """Layer 2. Anything with this method can be swapped in (fine-tuned encoder,
    TF-IDF baseline, an LLM judge via Ollama/OpenRouter...)."""

    name: str

    def classify(self, text: str) -> Classification: ...


def load_classifier(config: dict, root: Path) -> RequestClassifier:
    from ..model_store import ensure_model

    cfg = config["classifier"]
    # Fresh clone: fetch the trained model from the release; if that fails, fall back to
    # the baseline rather than crash.
    if cfg["backend"] == "transformer" and not ensure_model(cfg["model_dir"]):
        if not ensure_model(cfg["tfidf_path"]):
            raise FileNotFoundError(f"no classifier at {cfg['model_dir']} or {cfg['tfidf_path']}; "
                                    "run: python -m guardrails.train --backend tfidf (seconds) "
                                    "or python -m guardrails.train (fine-tuned, slower)")
        warnings.warn(f"{cfg['model_dir']} not found, using TF-IDF baseline {cfg['tfidf_path']}", stacklevel=2)
        cfg = {**cfg, "backend": "tfidf"}
    if cfg["backend"] == "transformer":
        from .transformer import TransformerClassifier

        return TransformerClassifier.load(root / cfg["model_dir"])
    if cfg["backend"] == "tfidf":
        from .tfidf import TfidfClassifier

        ensure_model(cfg["tfidf_path"])
        return TfidfClassifier.load(root / cfg["tfidf_path"])
    if cfg["backend"] == "llm_judge":
        from .llm_judge import LLMJudgeClassifier

        j = cfg["llm_judge"]
        return LLMJudgeClassifier(j["transport"], j["model"], j.get("host", "http://localhost:11434"))
    raise ValueError(f"unknown classifier backend {cfg['backend']!r}")
