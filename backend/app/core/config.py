from __future__ import annotations

import json
import secrets
from functools import lru_cache
from typing import Annotated, List, Literal, Optional

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# List-valued settings accept a comma-separated string in the environment
# (CORS_ORIGINS=http://a,http://b). NoDecode stops pydantic-settings from trying
# to JSON-decode the raw value before _split_csv below gets to see it.
CsvList = Annotated[List[str], NoDecode]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- application ---
    app_name: str = "Bhoomitra"
    app_env: Literal["development", "test", "staging", "production"] = "development"
    app_version: str = "1.0.0"
    api_v1_prefix: str = "/api/v1"
    debug: bool = False
    log_level: str = "INFO"
    log_json: bool = True

    # --- database ---
    database_url: str
    test_database_url: Optional[str] = None
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_echo: bool = False

    # --- auth / security ---
    jwt_secret_key: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 14
    password_reset_expire_minutes: int = 60
    activation_token_expire_hours: int = 48
    bcrypt_rounds: int = 12
    cors_origins: CsvList = ["http://localhost:3000"]
    cookie_secure: bool = False
    cookie_domain: Optional[str] = None
    rate_limit_enabled: bool = True
    rate_limit_default_per_minute: int = 300
    rate_limit_auth_per_minute: int = 10
    trusted_proxies: CsvList = []

    # --- cache / queue ---
    redis_url: Optional[str] = None
    celery_broker_url: Optional[str] = None
    celery_result_backend: Optional[str] = None
    task_execution_mode: Literal["celery", "inline", "thread"] = "thread"

    # --- search ---
    opensearch_url: Optional[str] = None
    opensearch_user: Optional[str] = None
    opensearch_password: Optional[str] = None
    opensearch_index_prefix: str = "bhoomitra"
    opensearch_verify_certs: bool = False

    # --- object storage ---
    storage_backend: Literal["local", "s3"] = "local"
    storage_local_path: str = "./var/storage"
    s3_endpoint_url: Optional[str] = None
    s3_access_key: Optional[str] = None
    s3_secret_key: Optional[str] = None
    s3_bucket: str = "bhoomitra"
    s3_region: str = "ap-south-1"
    s3_use_ssl: bool = False
    max_upload_mb: int = 100
    allowed_upload_mime: CsvList = [
        "application/pdf",
        "text/plain",
        "text/markdown",
        "text/csv",
        "application/json",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "image/png",
        "image/jpeg",
        "image/tiff",
        "application/geo+json",
        "application/zip",
    ]

    # --- AI ---
    ai_provider: Literal["openai", "local"] = "local"
    openai_api_key: Optional[str] = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_chat_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    embedding_provider: Literal["openai", "hashing"] = "hashing"
    embedding_dim: int = 1536
    rag_top_k: int = 8
    rag_min_score: float = 0.05
    chunk_size_chars: int = 900
    chunk_overlap_chars: int = 150
    ocr_enabled: bool = True
    ocr_min_chars_per_page: int = 40

    # --- email ---
    email_backend: Literal["console", "smtp"] = "console"
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from: str = "no-reply@bhoomitra.gov.in"
    frontend_base_url: str = "http://localhost:3000"

    # --- integrations ---
    geoboundaries_base_url: str = "https://www.geoboundaries.org/api/current/gbOpen"
    datagov_api_key: Optional[str] = None
    datagov_base_url: str = "https://api.data.gov.in/resource"
    stac_endpoint: Optional[str] = None

    # --- bootstrap ---
    bootstrap_superadmin_email: Optional[str] = None
    bootstrap_superadmin_password: Optional[str] = None
    demo_data_enabled: bool = True

    @field_validator("cors_origins", "allowed_upload_mime", "trusted_proxies", mode="before")
    @classmethod
    def _split_csv(cls, v):
        """Accept a comma-separated string, a JSON array, or a real list."""
        if isinstance(v, str):
            text = v.strip()
            if text.startswith("["):
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError:
                    pass
                else:
                    if isinstance(parsed, list):
                        return [str(p).strip() for p in parsed if str(p).strip()]
            return [p.strip() for p in text.split(",") if p.strip()]
        return v

    @model_validator(mode="after")
    def _validate(self):
        if self.app_env == "production":
            if self.debug:
                raise ValueError("DEBUG must be false in production")
            if self.jwt_secret_key in {"change-me", "dev-secret"} or len(self.jwt_secret_key) < 48:
                raise ValueError("JWT_SECRET_KEY must be a strong secret (>=48 chars) in production")
            if not self.cookie_secure:
                raise ValueError("COOKIE_SECURE must be true in production")
            if self.storage_backend == "s3" and not (self.s3_access_key and self.s3_secret_key):
                raise ValueError("S3 credentials are required when STORAGE_BACKEND=s3")
        if self.task_execution_mode == "celery" and not self.celery_broker_url:
            raise ValueError("CELERY_BROKER_URL is required when TASK_EXECUTION_MODE=celery")
        if self.ai_provider == "openai" and not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required when AI_PROVIDER=openai")
        if self.embedding_provider == "openai" and not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required when EMBEDDING_PROVIDER=openai")
        if self.embedding_dim <= 0 or self.embedding_dim > 4096:
            raise ValueError("EMBEDDING_DIM must be between 1 and 4096")
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_test(self) -> bool:
        return self.app_env == "test"

    @property
    def effective_celery_broker(self) -> Optional[str]:
        return self.celery_broker_url or self.redis_url


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()


def generate_secret() -> str:
    return secrets.token_urlsafe(48)
