# Guardrail safety eval: multihead:guardrail-modernbert-v2

Held-out set: 615 prompts (421 harmful incl. 140 urgent, 194 info). Policy 0.1.0 (cc1be8906a22). Screening latency 38.6 ms/request (CPU).

| metric | value |
|---|---|
| under_refusal | 0.048 |
| refusal_rate_harmful | 0.940 |
| hard_refuse_rate_harmful | 0.665 |
| emergency_recall | 0.900 |
| over_refusal | 0.015 |

## Emergency layer ablation (recall on urgent prompts)

| setup | emergency_recall | over_refusal |
|---|---|---|
| regex fast path only | 0.357 | 0.000 |
| classifier only | 0.879 | 0.015 |
| both (deployed) | 0.900 | 0.015 |

## Threshold sweep (over vs under refusal)

| shift | over_refusal | under_refusal | emergency_recall |
|---|---|---|---|
| -0.30 | 0.062 | 0.005 | 0.900 |
| -0.25 | 0.046 | 0.009 | 0.900 |
| -0.20 | 0.036 | 0.019 | 0.900 |
| -0.15 | 0.036 | 0.024 | 0.900 |
| -0.10 | 0.021 | 0.036 | 0.900 |
| -0.05 | 0.015 | 0.038 | 0.900 |
| +0.00 | 0.015 | 0.048 | 0.900 |
| +0.05 | 0.015 | 0.059 | 0.900 |
| +0.10 | 0.015 | 0.059 | 0.900 |
| +0.15 | 0.010 | 0.088 | 0.900 |
| +0.20 | 0.010 | 0.135 | 0.900 |
| +0.25 | 0.005 | 0.197 | 0.900 |
| +0.30 | 0.005 | 0.240 | 0.900 |

## Errors by attack type

| attack | n | errors | error rate |
|---|---|---|---|
| authority_claim | 36 | 1 | 0.03 |
| benign | 61 | 0 | 0.00 |
| benign_hard_negative | 88 | 2 | 0.02 |
| benign_wrapped | 18 | 0 | 0.00 |
| direct | 160 | 2 | 0.01 |
| emotional_pressure | 15 | 0 | 0.00 |
| fiction | 27 | 1 | 0.04 |
| format_constraint | 24 | 1 | 0.04 |
| hypothetical | 22 | 0 | 0.00 |
| indirect | 21 | 3 | 0.14 |
| instruction_override | 24 | 2 | 0.08 |
| multi_question | 15 | 0 | 0.00 |
| obfuscation | 21 | 1 | 0.05 |
| polite | 6 | 0 | 0.00 |
| roleplay | 22 | 0 | 0.00 |
| split_intent | 22 | 2 | 0.09 |
| third_party | 11 | 0 | 0.00 |
| translation | 22 | 8 | 0.36 |
