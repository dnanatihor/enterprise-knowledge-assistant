# Tech debt

- TD-KNOW-001: the corpus and audit file are local to one process. Exit criteria: `KNOW_DATABASE_URL` for chunks and a WORM object for the audit chain before a second replica.
- TD-KNOW-002: OIDC uses one pinned PEM. Exit criteria: JWKS with key ids, still rejecting `alg` other than ES256.
- TD-KNOW-003: the golden set is synthetic. Exit criteria: 100 human questions before the rollout list is cleared.
- TD-KNOW-004: seven-year retention is a policy. The file is not copied to WORM by this process yet.
