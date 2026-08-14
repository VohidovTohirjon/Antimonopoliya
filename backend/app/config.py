from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(PROJECT_ROOT / ".env", ".env"), extra="ignore")

    database_url: str = "postgresql+psycopg://raqobat:raqobat@localhost:5432/raqobat"
    secret_key: str = ""
    access_token_minutes: int = 480
    data_dir: Path = Path("data")
    max_upload_mb: int = 20
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174"
    groq_api_key: str = ""
    groq_model: str = ""
    groq_models: str = (
        "openai/gpt-oss-120b,qwen/qwen3.6-27b,openai/gpt-oss-20b,"
        "groq/compound,groq/compound-mini"
    )
    groq_force_unavailable: bool = False
    # Default deny: confidential/internal text may reach an external provider only
    # after an authorized deployment explicitly enables this policy.
    allow_external_confidential_ai: bool = False
    groq_timeout_seconds: float = 30.0
    groq_max_tokens: int = 3200
    embedding_model: str = "BAAI/bge-m3"
    embedding_backend: str = "sentence_transformers"
    embedding_dimensions: int = 1024
    embedding_warmup_on_startup: bool = True
    context_max_chars: int = 18000
    retrieval_min_score: float = 0.48
    retrieval_candidate_limit: int = 60
    # Password given to accounts that the explicitly confirmed local seed command
    # creates. It is never applied to accounts that already exist, is never used by
    # the application at runtime, and must not be set in a production deployment.
    local_seed_password: str = "12345678"

    @property
    def cors_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def groq_model_list(self) -> list[str]:
        configured = [item.strip() for item in self.groq_models.split(",") if item.strip()]
        if self.groq_model:
            configured = [self.groq_model] + [
                model for model in configured if model != self.groq_model
            ]
        return list(dict.fromkeys(configured))


@lru_cache
def get_settings() -> Settings:
    return Settings()
