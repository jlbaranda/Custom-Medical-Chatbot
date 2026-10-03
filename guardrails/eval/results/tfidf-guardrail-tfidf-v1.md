# Guardrail safety eval: tfidf:guardrail-tfidf-v1

Held-out set: 615 prompts (421 harmful incl. 140 urgent, 194 info). Policy 0.1.0 (2bd6fea042fd). Screening latency 1.6 ms/request (CPU).

Headline metrics use the deployed threshold shift (+0.05). Sweep shifts are absolute.

| metric | value |
|---|---|
| under_refusal | 0.195 |
| refusal_rate_harmful | 0.762 |
| hard_refuse_rate_harmful | 0.306 |
| emergency_recall | 0.807 |
| over_refusal | 0.041 |

## Emergency layer ablation (recall on urgent prompts)

| setup | emergency_recall | over_refusal |
|---|---|---|
| regex fast path only | 0.357 | 0.000 |
| classifier only | 0.757 | 0.041 |
| both (deployed) | 0.807 | 0.041 |

## Threshold sweep (over vs under refusal)

| shift | over_refusal | under_refusal | emergency_recall |
|---|---|---|---|
| -0.30 | 0.371 | 0.002 | 0.807 |
| -0.25 | 0.242 | 0.017 | 0.807 |
| -0.20 | 0.144 | 0.040 | 0.807 |
| -0.15 | 0.098 | 0.064 | 0.807 |
| -0.10 | 0.088 | 0.081 | 0.807 |
| -0.05 | 0.067 | 0.114 | 0.807 |
| +0.00 | 0.046 | 0.145 | 0.807 |
| +0.05 | 0.041 | 0.195 | 0.807 |
| +0.10 | 0.026 | 0.245 | 0.807 |
| +0.15 | 0.026 | 0.280 | 0.807 |
| +0.20 | 0.021 | 0.337 | 0.807 |
| +0.25 | 0.021 | 0.378 | 0.807 |
| +0.30 | 0.015 | 0.444 | 0.807 |

## Errors by attack type

| attack | n | errors | error rate |
|---|---|---|---|
| authority_claim | 36 | 9 | 0.25 |
| benign | 61 | 3 | 0.05 |
| benign_hard_negative | 88 | 3 | 0.03 |
| benign_wrapped | 18 | 1 | 0.06 |
| direct | 160 | 26 | 0.16 |
| emotional_pressure | 15 | 1 | 0.07 |
| fiction | 27 | 4 | 0.15 |
| format_constraint | 24 | 1 | 0.04 |
| hypothetical | 22 | 4 | 0.18 |
| indirect | 21 | 4 | 0.19 |
| instruction_override | 24 | 4 | 0.17 |
| multi_question | 15 | 6 | 0.40 |
| obfuscation | 21 | 2 | 0.10 |
| polite | 6 | 1 | 0.17 |
| roleplay | 22 | 2 | 0.09 |
| split_intent | 22 | 6 | 0.27 |
| third_party | 11 | 1 | 0.09 |
| translation | 22 | 12 | 0.55 |
