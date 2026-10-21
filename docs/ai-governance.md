# AI governance

## Decision

The assistant may answer only from chunks the caller is allowed to read. Low confidence escalates to a human with the question and the score.

## Controls

- Model: pinned `gpt-4o-mini-2024-07-18`. No other model id without an ADR.
- Embeddings: `local-hash-embed-v1`, 384 dimensions. A mismatch refuses search until rebuild.
- Evaluation: 100 synthetic departmental facts plus refusal prompts. Faithfulness must stay above 0.85. A human-authored set is still required before broad rollout (tech debt).
- Online signals: cache hit, refusal, and cost are on the audit event. A sampled human review of refusals is the online check. There is no second model grading production answers in this release.
- Red team: employee versus payroll ACL, cross-role cache, dev token against oidc, and audit tamper are automated tests.

## Data

Questions and documents are Confidential. They are not written to logs or to the audit body. The provider sees only eligible chunks on the answer path.
