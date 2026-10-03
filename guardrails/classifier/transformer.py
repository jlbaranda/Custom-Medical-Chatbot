from __future__ import annotations

import json
from pathlib import Path

import torch
from torch import nn
from transformers import AutoModel, AutoTokenizer

from ..normalize import normalize
from ..types import INTENTS, Classification

# Fine-tuned encoder with three heads on one shared backbone:
#   intent    - softmax over INTENTS
#   personal  - sigmoid, is the request about the user / someone they know
#   injection - sigmoid, jailbreak / roleplay / hypothetical framing
# Backbone is configurable (ModernBERT by default; BiomedBERT etc. for comparison).

DEFAULT_BACKBONE = "answerdotai/ModernBERT-base"
MAX_LEN = 128


class MultiHeadClassifier(nn.Module):
    def __init__(self, backbone_name: str, dropout: float = 0.1):
        super().__init__()
        self.backbone = AutoModel.from_pretrained(backbone_name)
        hidden = self.backbone.config.hidden_size
        self.dropout = nn.Dropout(dropout)
        self.intent_head = nn.Linear(hidden, len(INTENTS))
        self.personal_head = nn.Linear(hidden, 1)
        self.injection_head = nn.Linear(hidden, 1)

    def forward(self, input_ids, attention_mask):
        hidden = self.backbone(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state
        # Mean pooling over real tokens; more stable than CLS across backbones.
        mask = attention_mask.unsqueeze(-1).to(hidden.dtype)
        pooled = self.dropout((hidden * mask).sum(1) / mask.sum(1).clamp(min=1.0))
        return (
            self.intent_head(pooled),
            self.personal_head(pooled).squeeze(-1),
            self.injection_head(pooled).squeeze(-1),
        )


class TransformerClassifier:
    def __init__(self, model: MultiHeadClassifier, tokenizer, name: str, temperature: float = 1.0):
        self.model = model.eval()
        self.tokenizer = tokenizer
        self.name = name
        # Temperature scaling fitted on the validation set so probabilities are calibrated,
        # which is what makes policy thresholds meaningful.
        self.temperature = temperature

    @torch.inference_mode()
    def classify_batch(self, texts: list[str]) -> list[Classification]:
        enc = self.tokenizer([normalize(t) for t in texts], padding=True, truncation=True,
                             max_length=MAX_LEN, return_tensors="pt")
        intent_logits, personal_logit, injection_logit = self.model(enc["input_ids"], enc["attention_mask"])
        intent_p = torch.softmax(intent_logits / self.temperature, dim=-1)
        personal_p = torch.sigmoid(personal_logit)
        injection_p = torch.sigmoid(injection_logit)
        return [
            Classification(
                intent_probs={intent: float(intent_p[row, k]) for k, intent in enumerate(INTENTS)},
                personal=float(personal_p[row]),
                injection=float(injection_p[row]),
                model=self.name,
            )
            for row in range(len(texts))
        ]

    def classify(self, text: str) -> Classification:
        return self.classify_batch([text])[0]

    def save(self, out_dir: Path, backbone_name: str, metrics: dict | None = None) -> None:
        out_dir.mkdir(parents=True, exist_ok=True)
        self.model.backbone.save_pretrained(out_dir / "backbone")
        self.tokenizer.save_pretrained(out_dir / "backbone")
        heads = {k: v for k, v in self.model.state_dict().items() if not k.startswith("backbone.")}
        torch.save(heads, out_dir / "heads.pt")
        meta = {"name": self.name, "backbone": backbone_name, "intents": [i.value for i in INTENTS],
                "temperature": self.temperature, "max_len": MAX_LEN, "metrics": metrics or {}}
        (out_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, model_dir: Path) -> "TransformerClassifier":
        meta = json.loads((model_dir / "meta.json").read_text(encoding="utf-8"))
        if meta["intents"] != [i.value for i in INTENTS]:
            raise ValueError("model was trained with a different intent list; retrain it")
        model = MultiHeadClassifier(str(model_dir / "backbone"))
        model.load_state_dict(torch.load(model_dir / "heads.pt", map_location="cpu"), strict=False)
        tokenizer = AutoTokenizer.from_pretrained(model_dir / "backbone")
        return cls(model, tokenizer, f"multihead:{model_dir.name}", meta.get("temperature", 1.0))
