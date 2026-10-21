# ADR-001: RBAC filters chunks before ranking and before the prompt

## Status

Accepted

## Context

Hiding a citation in the UI, or telling the model not to reveal a document, still sends the restricted text to the provider.

## Decision

A chunk is eligible only when `tenant_id` matches the token and `chunk.acl` intersects the token roles. `Corpus.search` applies that filter before dense and sparse ranking. The SQL contract is `ACL_FILTER_SQL` (`EXISTS` on `chunk_acl`). The answer prompt contains only eligible chunk text. Escalation receives the question and the confidence score, never retrieved text. The cache key includes tenant, sorted roles, the query hash, and the embedding model id.

## Constraints

- Ingest requires `knowledge-admin` and a non-empty ACL.
- Query requires `knowledge-user`.
- An empty rollout list means every team. A non-empty list rejects other teams with 403.
- Dev HMAC tokens are refused when `auth_mode=oidc`.

## Options

- Prompt the model with all chunks and ask it to respect roles. Rejected.
- Filter only the displayed citations. Rejected: the prompt would already have leaked.

## Failure modes

- A new retrieval path that forgets the predicate. The payroll test asserts the restricted sentence is absent from the employee answer and from the model transcript.
- A cache keyed only on the query would serve a privileged answer to a narrower role. Roles are part of the key.

## Owner

Knowledge assistant. Next action: keep the in-memory corpus until `KNOW_DATABASE_URL` is the production system of record.
