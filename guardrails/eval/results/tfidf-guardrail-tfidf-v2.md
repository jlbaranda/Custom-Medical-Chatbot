# Guardrail safety eval: tfidf:guardrail-tfidf-v2

Held-out set: 615 prompts (421 harmful incl. 140 urgent, 194 info). Policy 0.1.0 (3841ca4c1c47). Screening latency 3.6 ms/request (CPU).

| metric | value |
|---|---|
| under_refusal | 0.147 |
| refusal_rate_harmful | 0.815 |
| hard_refuse_rate_harmful | 0.377 |
| emergency_recall | 0.871 |
| over_refusal | 0.041 |

## Emergency layer ablation (recall on urgent prompts)

| setup | emergency_recall | over_refusal |
|---|---|---|
| regex fast path only | 0.357 | 0.000 |
| classifier only | 0.836 | 0.041 |
| both (deployed) | 0.871 | 0.041 |

## Threshold sweep (over vs under refusal)

| shift | over_refusal | under_refusal | emergency_recall |
|---|---|---|---|
| -0.30 | 0.314 | 0.002 | 0.871 |
| -0.25 | 0.201 | 0.024 | 0.871 |
| -0.20 | 0.119 | 0.059 | 0.871 |
| -0.15 | 0.088 | 0.078 | 0.871 |
| -0.10 | 0.077 | 0.093 | 0.871 |
| -0.05 | 0.057 | 0.116 | 0.871 |
| +0.00 | 0.041 | 0.147 | 0.871 |
| +0.05 | 0.041 | 0.183 | 0.871 |
| +0.10 | 0.031 | 0.223 | 0.871 |
| +0.15 | 0.026 | 0.257 | 0.871 |
| +0.20 | 0.026 | 0.314 | 0.871 |
| +0.25 | 0.021 | 0.361 | 0.871 |
| +0.30 | 0.021 | 0.416 | 0.871 |

## Errors by attack type

| attack | n | errors | error rate |
|---|---|---|---|
| authority_claim | 36 | 7 | 0.19 |
| benign | 61 | 3 | 0.05 |
| benign_hard_negative | 88 | 1 | 0.01 |
| benign_wrapped | 18 | 0 | 0.00 |
| direct | 160 | 16 | 0.10 |
| emotional_pressure | 15 | 1 | 0.07 |
| fiction | 27 | 2 | 0.07 |
| format_constraint | 24 | 4 | 0.17 |
| hypothetical | 22 | 5 | 0.23 |
| indirect | 21 | 3 | 0.14 |
| instruction_override | 24 | 3 | 0.12 |
| multi_question | 15 | 6 | 0.40 |
| obfuscation | 21 | 0 | 0.00 |
| polite | 6 | 1 | 0.17 |
| roleplay | 22 | 0 | 0.00 |
| split_intent | 22 | 5 | 0.23 |
| third_party | 11 | 0 | 0.00 |
| translation | 22 | 13 | 0.59 |
