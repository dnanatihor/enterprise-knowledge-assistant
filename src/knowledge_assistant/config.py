"""Process configuration. Production identity is OIDC with a pinned ES256 key."""

from __future__ import annotations

from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from knowledge_assistant.platform import (
    DEFAULT_INPUT_USD_PER_TOKEN,
    DEFAULT_OUTPUT_USD_PER_TOKEN,
    load_vault_key,
)

# Project root, so `poetry run uvicorn` picks up .env without a flag.
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="KNOW_",
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "dev"
    service_name: str = "enterprise-knowledge-assistant"
    llm_mode: str = "auto"
    llm_api_key: SecretStr | None = None
    vault_secret_path: str | None = None
    auth_mode: str = "dev"
    dev_auth_secret: str = "dev-only-not-for-production"
    oidc_public_key_pem: str = ""
    oidc_issuer: str = "https://issuer.local"
    oidc_audience: str = "knowledge-assistant"
    rollout_teams: str = ""
    embedding_model_id: str = "local-hash-embed-v1"
    confidence_threshold: float = 0.45
    query_budget_usd: float = 0.05
    user_budget_usd: float = 1.0
    audit_path: str = ""
    database_url: str | None = None
    input_usd_per_token: float = DEFAULT_INPUT_USD_PER_TOKEN
    output_usd_per_token: float = DEFAULT_OUTPUT_USD_PER_TOKEN
    llm_timeout_s: float = 2.0
    rate_limit_per_minute: int = 120

    @property
    def resolved_api_key(self) -> SecretStr | None:
        env_key = self.llm_api_key.get_secret_value() if self.llm_api_key else None
        return load_vault_key(self.vault_secret_path, app_env=self.app_env, env_key=env_key)

    @property
    def teams(self) -> set[str]:
        return {item.strip() for item in self.rollout_teams.split(",") if item.strip()}
