from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://matcher:matcher@localhost:5432/matcher"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "change-me-in-production"
    access_ttl_minutes: int = 15
    refresh_ttl_days: int = 7
    # "minilm" = sentence-transformers all-MiniLM-L6-v2, "hash" = dependency-free fallback
    embedder: str = "hash"
    # "arq" = Redis-backed worker, "inline" = run the job in the API process (tests, no-Redis dev)
    queue: str = "inline"
    upload_dir: str = "./uploads"
    max_upload_bytes: int = 5 * 1024 * 1024
    ann_candidates: int = 200
    cors_origins: str = "http://localhost:3000"


@lru_cache
def get_settings() -> Settings:
    return Settings()
