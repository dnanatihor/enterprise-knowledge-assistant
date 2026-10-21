# Enterprise Knowledge Assistant

Internal assistant for policies, tickets, wiki pages, database rows, and PDFs. Access is decided in the query, before any model sees text. An append-only hash chain records each query. Teams outside the rollout list are rejected.

## Run

```bash
poetry install
poetry run uvicorn knowledge_assistant.main:app --reload --port 8005
```

Dev tokens are HMAC tokens from `POST /api/v1/auth/token`. `KNOW_AUTH_MODE=oidc` requires `KNOW_OIDC_PUBLIC_KEY_PEM` and rejects tokens that start with `dev.`. Production (`KNOW_APP_ENV=prod`) also requires `llm_api_key` in the vault file at `KNOW_VAULT_SECRET_PATH`.

## API

- `POST /api/v1/documents` requires role `knowledge-admin`
- `POST /api/v1/query` requires role `knowledge-user`
- `GET /api/v1/audit/verify`
- `POST /api/v1/eval` requires `knowledge-admin`

## Decisions

See `docs/adr`, `docs/rollout.md`, and `docs/incident-rollback.md`. Budget: under $0.05 per query, p95 under 2 seconds, faithfulness above 0.85.
