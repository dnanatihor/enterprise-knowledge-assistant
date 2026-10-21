# Incident and rollback

## Restricted text in a model transcript

Treat it as a data incident. Disable the rollout list (`KNOW_ROLLOUT_TEAMS=none` with no such team) so queries return 403. Preserve the audit file. Identify the correlation id. Do not delete audit lines.

## Bad release

Roll back the image. The document schema is additive (chunks and `chunk_acl`). Do not run a down migration during the incident. The previous image still reads the same columns.

## Key compromise

Remove `KNOW_VAULT_SECRET_PATH` from the deployment and rotate the vault value. OIDC: replace `KNOW_OIDC_PUBLIC_KEY_PEM` with the new key and reject the old one. Dev HMAC secrets are not used in oidc mode.

## Audit gap

If the process cannot append, query returns an error rather than answering without a record. Restore disk space or the volume, then retry. Do not switch the audit writer to an in-memory buffer.
