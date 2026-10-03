# Guardrails

Safety layer for the medical Q&A chatbot. Every request passes through six layers before and after the LLM. Policy (thresholds, models, templates) lives in [`policy.toml`](policy.toml), not in code.

```
question
  │
  0  PHI redaction ............ pii.py           names, phones, emails, MRNs, dates → [TYPE]
  1  Emergency fast path ...... emergency.py     regex, recall-first → 911 / 988 / Poison Control first
  2  Request classifier ....... classifier/      fine-tuned ModernBERT: intent + P(personal) + P(injection)
  3  Graded policy ............ policy.py        answer / redirect / refuse per intent, tunable thresholds
  4  Retrieval gate ........... retrieval.py     BM25 candidates → MedCPT cross-encoder; weak match = no answer
     (LLM generates) .......... generation.py    Qwen via Ollama later; extractive stand-in for now
  5  Output check ............. output_check.py  every sentence cited + grounded; numbers must be in source; no doses
  6  Decision log ............. audit.py         which layer fired and why; never the question or answer text
```

## Usage

```powershell
python -m pip install -r requirements.txt          # ~1 GB incl. CPU torch
python -m guardrails.train --backend tfidf          # baseline classifier, seconds
python -m guardrails.train --out models/guardrail-modernbert-v2   # fine-tuned (CPU: ~40 min, ~2.5 GB RAM; --low-memory --batch-size 8 for less)
python scripts/ask.py --trace "how much tylenol can my 3 year old have"
python -m guardrails.eval.run_eval                  # safety eval + threshold sweep → guardrails/eval/results/
python -m guardrails.eval.experiments               # train + eval every variant, writes results/summary.md
python -m guardrails.eval.calibrate_gate            # re-pick the retrieval gate threshold after corpus changes
```

In code:

```python
from guardrails import GuardedChatbot
from guardrails.generation import OllamaGenerator
bot = GuardedChatbot.from_config()                   # extractive stand-in generator
bot = GuardedChatbot.from_config(generator=OllamaGenerator("qwen2.5:3b"))   # once Qwen is set up
r = bot.ask("what are the symptoms of anemia")
r.action, r.text, r.citations
```

Swap points (all protocols, no subclassing needed): `RequestClassifier`, `Retriever` (e.g. the team's MedCPT/BiomedBERT embedding retriever), `Generator`. Without a trained transformer the pipeline falls back to the TF-IDF baseline with a warning.

## Actions

| action | when | user sees |
|---|---|---|
| `emergency` | layer 1 regex, or classifier P(emergency)+P(self_harm) ≥ 0.35 | emergency services first, nothing else |
| `refuse` | risk ≥ intent's refuse threshold, or risky intent + jailbreak framing | why not + who to ask |
| `redirect` | risk in the redirect band | decline the personal part + cited general info on the topic |
| `answer` | risk below every redirect threshold | cited answer (+ 911 banner if the topic is an emergency) |
| `no_support` | retrieval gate or output check leaves nothing | "not in my trusted sources" |

Risk is `P(intent) × (0.6 + 0.4 × P(personal))`, so "usual adult dose of X" scores lower than "how much X for my kid".

## Classifier

Multi-head encoder (`classifier/transformer.py`): one backbone, three heads (6-way intent softmax, personal sigmoid, injection sigmoid), mean pooling, temperature-calibrated on validation so thresholds mean something. Backbone is a flag:

```powershell
python -m guardrails.train --backbone answerdotai/ModernBERT-base                                  # default
python -m guardrails.train --backbone microsoft/BiomedNLP-BiomedBERT-base-uncased-abstract-fulltext --out models/guardrail-biomedbert-v2
python -m guardrails.train --backend tfidf                                                         # baseline
python -m guardrails.train --exclude adversarial --out models/guardrail-modernbert-v1              # ablation: no adversarial data
```

Optional third backend, `llm_judge` in `policy.toml`: an LLM labels the request with the same schema. `transport = "ollama"` runs the team's local Qwen (no key, nothing leaves the machine); `"openrouter"` needs `OPENROUTER_API_KEY` and only ever receives PHI-redacted text. Unparseable judge output fails safe (treated as risky, so it is redirected).

Training data (`data/train_*.jsonl`, ~2.1k prompts) is synthetic, LLM-written once, labeled with intent / personal / injection, including hard negatives (personal context + general question) and jailbreak wrappers around harmless questions. The held-out red-team set (`eval/heldout.jsonl`, 615 prompts, 18 attack types) was written by separate generators that never saw the training files, and is excluded from training by exact match.

## Eval (no LLM needed)

`run_eval.py` reports on the held-out set:

- **under-refusal**: harmful prompt answered normally
- **over-refusal**: info prompt redirected / refused
- **emergency recall**: urgent prompts that got the emergency response
- emergency-layer ablation (regex only / classifier only / both)
- errors by attack type (roleplay, obfuscation, authority claim, ...)
- threshold sweep → `results/<model>_sweep.csv`, the over- vs under-refusal tradeoff curve

`experiments.py` runs every variant (TF-IDF / ModernBERT / BiomedBERT, with and without adversarial training data) and writes `results/summary.md`.

Retrieval gate: `calibrate_gate.py` scores 80 labeled questions (in-corpus vs not) with the MedCPT cross-encoder and picks the threshold (currently 9.5, balanced accuracy 0.96). Raw BM25 scores were not usable as a gate: they let "how do I fix my car brakes" through and blocked "symptoms of anemia".

Answer-quality eval (faithfulness, RAGAS-style) is added once the real LLM is in.

## Hazard → control table (device-readiness)

Intended use is general health information, which keeps the product outside medical-device software by default. Each hazard has a control and a test (`tests/test_guardrails.py`, IDs `GR-xx`), so the same evidence supports an IEC 62304 / ISO 14971 file if the project ever moves into that scope.

| ID | hazard | control | evidence |
|---|---|---|---|
| GR-01 | user in an emergency gets an information answer | layer 1 regex + classifier backup; emergency response replaces everything else | tests GR-01, eval emergency recall |
| GR-02 | bot diagnoses, doses, or makes treatment decisions | layer 2-3 graded policy; layer 5 drops dose amounts and "you have X" claims | tests GR-02/04, eval under-refusal |
| GR-03 | unsupported or hallucinated claims | layer 4 gate (cross-encoder threshold); layer 5 citation + grounding + number checks | tests GR-03/04 |
| GR-04 | jailbreak / roleplay bypass | injection head escalates risky asks to refuse; normalization undoes obfuscation | eval by attack type |
| GR-05 | PHI leakage into logs or third-party models | layer 0 redaction before any model; log stores no text | tests GR-05 |
| GR-06 | over-refusal makes the tool useless and pushes users to worse sources | redirect action (still gives cited info); thresholds tuned on over-refusal | eval over-refusal, sweep |

Each log line records `policy_version`, `policy_hash`, and the model names, so any decision can be traced back to the exact configuration that made it.
