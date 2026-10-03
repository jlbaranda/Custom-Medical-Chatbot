# Guardrail classifier comparison (held-out red-team set)

| model | under_refusal | over_refusal | emergency_recall | refusal_rate_harmful | latency |
|---|---|---|---|---|---|
| guardrail-tfidf-v1 | 0.145 | 0.046 | 0.807 | 0.826 | 3.8 ms |
| guardrail-tfidf-v2 | 0.147 | 0.041 | 0.871 | 0.815 | 3.4 ms |
| guardrail-modernbert-v1 | 0.048 | 0.062 | 0.843 | 0.947 | 65.4 ms |
| guardrail-modernbert-v2 | 0.048 | 0.015 | 0.900 | 0.940 | 38.6 ms |
| guardrail-biomedbert-v2 | 0.017 | 0.031 | 0.886 | 0.979 | 26.6 ms |
