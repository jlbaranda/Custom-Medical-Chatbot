# Guardrail safety eval: multihead:guardrail-modernbert-v1

Held-out set: 615 prompts (421 harmful incl. 140 urgent, 194 info). Policy 0.1.0 (cc1be8906a22). Screening latency 65.4 ms/request (CPU).

| metric | value |
|---|---|
| under_refusal | 0.048 |
| refusal_rate_harmful | 0.947 |
| hard_refuse_rate_harmful | 0.705 |
| emergency_recall | 0.843 |
| over_refusal | 0.062 |

## Emergency layer ablation (recall on urgent prompts)

| setup | emergency_recall | over_refusal |
|---|---|---|
| regex fast path only | 0.357 | 0.000 |
| classifier only | 0.779 | 0.062 |
| both (deployed) | 0.843 | 0.062 |

## Threshold sweep (over vs under refusal)

| shift | over_refusal | under_refusal | emergency_recall |
|---|---|---|---|
| -0.30 | 0.206 | 0.009 | 0.843 |
| -0.25 | 0.160 | 0.014 | 0.843 |
| -0.20 | 0.129 | 0.021 | 0.843 |
| -0.15 | 0.098 | 0.021 | 0.843 |
| -0.10 | 0.088 | 0.036 | 0.843 |
| -0.05 | 0.072 | 0.036 | 0.843 |
| +0.00 | 0.062 | 0.048 | 0.843 |
| +0.05 | 0.057 | 0.055 | 0.843 |
| +0.10 | 0.057 | 0.064 | 0.843 |
| +0.15 | 0.051 | 0.086 | 0.843 |
| +0.20 | 0.041 | 0.114 | 0.843 |
| +0.25 | 0.041 | 0.154 | 0.843 |
| +0.30 | 0.041 | 0.197 | 0.843 |

## Errors by attack type

| attack | n | errors | error rate |
|---|---|---|---|
| authority_claim | 36 | 1 | 0.03 |
| benign | 61 | 0 | 0.00 |
| benign_hard_negative | 88 | 1 | 0.01 |
| benign_wrapped | 18 | 9 | 0.50 |
| direct | 160 | 3 | 0.02 |
| emotional_pressure | 15 | 0 | 0.00 |
| fiction | 27 | 1 | 0.04 |
| format_constraint | 24 | 0 | 0.00 |
| hypothetical | 22 | 1 | 0.05 |
| indirect | 21 | 2 | 0.10 |
| instruction_override | 24 | 4 | 0.17 |
| multi_question | 15 | 1 | 0.07 |
| obfuscation | 21 | 1 | 0.05 |
| polite | 6 | 0 | 0.00 |
| roleplay | 22 | 0 | 0.00 |
| split_intent | 22 | 3 | 0.14 |
| third_party | 11 | 1 | 0.09 |
| translation | 22 | 4 | 0.18 |
