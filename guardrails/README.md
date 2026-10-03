# Guardrails

Safety layer around the chatbot: emergency detection, refusal of diagnosis / dosing / personal treatment advice, "no source, no answer", and cited-output checks.

## Setup

```powershell
git pull
python -m pip install -r requirements.txt     # one time, ~1 GB (CPU torch)
python scripts/run_ingestion.py                # if data/chunks/chunks.jsonl is not built yet
```

The trained classifier (408 MB) downloads itself on first run. Nothing to train.

## Try it

```powershell
python scripts/ask.py "what are the symptoms of anemia"
python scripts/ask.py --trace "how much tylenol can my 3 year old have"    # shows which layer decided and why
python scripts/ask.py --chat                                               # multi-turn conversation
```

## Use it in code

```python
from guardrails import GuardedChatbot
from guardrails.generation import OllamaGenerator

bot = GuardedChatbot.from_config()                                         # stand-in answer generator
bot = GuardedChatbot.from_config(generator=OllamaGenerator("qwen2.5:3b"))  # real LLM via Ollama
r = bot.ask("what are the symptoms of anemia")
r.action      # answer | redirect | refuse | emergency | no_support
r.text        # what to show the user
r.citations   # sources used
```

Multi-turn: pass the conversation so far (standard chat format, without the new question). Route every user message through `bot.ask`; calling the LLM directly skips the guardrails.

```python
history = [{"role": "user", "content": "who should get a flu vaccine"},
           {"role": "assistant", "content": "..."}]
r = bot.ask("what about for kids?", history=history)
```

With history, a follow-up is searched together with the question it follows, a risky request split across messages is judged as a whole, and an emergency keeps the emergency response for the next 2 turns (`[conversation]` in `policy.toml`).

To plug in your own parts, pass them to `from_config`:

| part | what to pass | interface |
|---|---|---|
| LLM | `generator=` | `.generate(question, passages) -> str`, each sentence ending in `[n]` |
| retriever | `retriever=` | `.search(query, k) -> list[Passage]` |

## Change behaviour

Everything tunable is in [`policy.toml`](policy.toml): which classifier, refusal thresholds, retrieval gate threshold, log path. No code changes needed.

| want | change |
|---|---|
| refuse more / less | `threshold_shift` (negative = stricter) |
| different classifier | `[classifier] model_dir` (see models below) |
| baseline or LLM-judge classifier | `[classifier] backend = "tfidf"` or `"llm_judge"` |
| stricter "no source, no answer" | `min_rerank_score` |
| LLM does not write `[n]` citations reliably (answers come back as "not in my trusted sources") | `[output] require_citations = false` |

## Models

```powershell
python -m guardrails.model_store          # the default model (also happens automatically)
python -m guardrails.model_store --all    # all 5, for the comparison experiments
```

| model | role |
|---|---|
| `guardrail-biomedbert-v2` | default |
| `guardrail-modernbert-v2`, `-v1` | comparison, and ablation without adversarial training data |
| `guardrail-tfidf-v2.pkl`, `-v1.pkl` | baseline |

Retrain instead of downloading (CPU, ~30 min each, ~2.5 GB RAM; add `--low-memory --batch-size 8` for less):

```powershell
python -m guardrails.train --backbone microsoft/BiomedNLP-BiomedBERT-base-uncased-abstract-fulltext --out models/guardrail-biomedbert-v2
python -m guardrails.train --backend tfidf --out models/guardrail-tfidf-v2.pkl
```

Publishing new models (maintainers): `python -m guardrails.model_store --pack <release download URL>`, upload `models/_release/*` to a new GitHub release, commit `models_manifest.json`.

## Evaluate

```powershell
python -m pytest -q                              # unit tests
python -m guardrails.eval.run_eval               # safety metrics + threshold sweep for the default model
python -m guardrails.eval.experiments --eval-only   # all models -> guardrails/eval/results/summary.md
python -m guardrails.eval.calibrate_gate         # re-pick the retrieval gate threshold after the corpus changes
```

Current results on the 615-prompt held-out red-team set: [`eval/results/summary.md`](eval/results/summary.md).

- **under-refusal**: harmful prompt answered normally
- **over-refusal**: info prompt redirected or refused
- **emergency recall**: share of urgent prompts that got the emergency response

## How it works (short)

```
0  PHI redaction ........ pii.py           names, phones, emails, MRNs -> [TYPE]
1  Emergency fast path .. emergency.py     regex, recall-first -> 911 / 988 / Poison Control
2  Request classifier ... classifier/      intent + P(personal) + P(injection)
3  Graded policy ........ policy.py        answer / redirect / refuse
4  Retrieval gate ....... retrieval.py     BM25 -> MedCPT cross-encoder; weak match = no answer
5  Output check ......... output_check.py  cited, grounded, numbers in source, no doses
6  Decision log ......... audit.py         which layer fired and why, never the text
```

Training data (`data/train_*.jsonl`, ~2.1k prompts) and the held-out set (`eval/heldout.jsonl`) are synthetic and were written by separate generators; held-out prompts are excluded from training.

## Hazard -> control (device-readiness)

Intended use is general health information. Each hazard has a control and tests (`tests/test_guardrails.py`, IDs `GR-xx`).

| ID | hazard | control |
|---|---|---|
| GR-01 | emergency gets an information answer | layers 1-2, emergency response replaces everything |
| GR-02 | bot diagnoses, doses, or decides treatment | layers 2-3, plus layer 5 dropping doses and "you have X" |
| GR-03 | unsupported or hallucinated claims | layer 4 gate, layer 5 citation and number checks |
| GR-04 | jailbreak / roleplay bypass | injection head escalates to refuse; text normalization |
| GR-05 | PHI in logs or third-party models | layer 0 redaction; text-free log |
| GR-06 | over-refusal makes the tool useless | redirect action; thresholds tuned on over-refusal |
| GR-07 | risky request split across turns, or emergency dropped on a follow-up | follow-ups judged with prior turns (stricter decision wins); sticky emergency |
