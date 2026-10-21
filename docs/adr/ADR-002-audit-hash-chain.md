# ADR-002: Queries are appended to a hash-chained log

## Status

Accepted

## Context

A support investigation needs to show which chunks were eligible for a subject without storing the document body in the log.

## Decision

Each query appends one JSON object: event id, event type, source, timestamp, correlation id, schema version, tenant, subject, roles, query hash, chunk ids, answer hash, refusal flag, cache flag, and cost. The record hash is SHA-256 of the previous hash plus the canonical body. The log has no update and no delete method. `GET /api/v1/audit/verify` recomputes the chain. Retention is seven years by archival to a WORM store. This process does not run a deletion job.

## Constraints

- The audit body does not contain the question text or the answer text.
- A cache hit is still audited, with cost 0.
- Tampering with a line makes `verify` return `intact: false`.

## Options

- A mutable table of queries. Rejected: an administrator could change history.
- Log the full prompt. Rejected: it copies restricted text into a second store.

## Failure modes

- A disk edit after a crash. Verification fails closed. Restore from the WORM copy. Do not rewrite the chain to make it pass.
- The in-process file is one replica's log. A second replica needs an append-only shared log before it serves traffic.

## Owner

Knowledge assistant.
