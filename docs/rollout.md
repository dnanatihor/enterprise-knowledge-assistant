# Rollout

## Decision

Ship to named teams first. `KNOW_ROLLOUT_TEAMS` is a comma-separated allow list. Empty means all teams.

## Sequence

1. Deploy with `KNOW_ROLLOUT_TEAMS=pilot` and `KNOW_AUTH_MODE=oidc`.
2. Confirm a pilot token can query and a token whose `team` claim is outside the list receives 403.
3. Watch cost per query and the refusal rate for one week.
4. Add the next team. Do not clear the list until the on-call owner accepts full availability.

## Rollback

Set `KNOW_ROLLOUT_TEAMS` back to the previous list and restart. In-flight requests finish. No data migration is required. Documents and the audit log stay.

## Owner

Knowledge assistant on-call. Next action after pilot week: add one adjacent team, not the whole company.
