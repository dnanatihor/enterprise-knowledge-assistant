# Runbook

## A user reports a missing document

Confirm the token roles intersect the document ACL and the tenant matches. A refusal with escalation means the filter returned nothing or the score was under 0.45. Do not paste the document into a prompt to check.

## Audit verify is false

Stop writes to that file. Compare it with the WORM copy. Do not edit the file to restore a hash. Page the owner of the knowledge assistant and follow `docs/incident-rollback.md`.

## Budget 402

`query-budget` or `user-budget` is working as designed. Raising `KNOW_USER_BUDGET_USD` is a budget decision, not an incident fix.

## Correlation

Use `X-Correlation-ID` and `X-Trace-ID`. The audit row stores the same correlation id and the query hash, not the question.
