# Enterprise knowledge architecture

## Decision

Verify the caller, filter chunks by tenant and role, then answer from those chunks or escalate with no document text. The chunk store is the system of record for content. The audit log is the system of record for access events. They are not the same record.

## Constraints

- Classification: document bodies and questions are Confidential. The audit log stores identifiers and hashes, which are still Confidential and are retained seven years.
- Secrets: production model keys come from the vault file. OIDC verification uses a pinned ES256 public key. Dev HMAC is not valid in oidc mode.
- Every request gets a correlation id. Logs do not contain prompts, documents, or tokens.
- Per-query budget $0.05. Per-user budget $1.00. Cache TTL 60 seconds.

## Options

- The query graph is rewrite, retrieve, then answer or escalate. Escalation uses a deep agent and is not given chunk text.
- Neural rerank. Trial only. The adopted rerank is lexical overlap.

## SLO

Under $0.05 per query, p95 under 2 seconds, faithfulness above 0.85 on the 100-case gate.

## Radar

- Adopt: query-time ACL, hash-chained audit, pinned mini snapshot, local hash embeddings, Poetry, LangChain message types.
- Trial: deepagents for escalation drafts. ES256 verification against a pinned key (JWKS refresh is not adopted).
- Hold: prompt-only access control. Dev tokens in production. MD5 or unsigned tokens.

## Adversarial review

- A payroll document ACL'd to `payroll-confidential` must not appear in an employee transcript. Covered by `tests/test_knowledge.py`.
- A `dev.` token presented to oidc mode is rejected before search.
- Escalation cannot quote a document it was not given. The prompt builder omits chunk text.
