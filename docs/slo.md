# SLOs

- Latency: p95 under 2 seconds.
- Cost: under $0.05 per query, including a cache hit at $0. A user whose recorded spend has reached $1.00 is rejected before the model call.
- Faithfulness: above 0.85 on the golden gate. Recall@5 at least 0.95. Refusal accuracy 1.0 on the held-out prompts.
- Audit: `verify` returns intact after every successful query path in the RBAC test, and false after a one-line edit.
