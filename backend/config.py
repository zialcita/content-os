from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        extra="ignore",
    )

    app_env: str = "development"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:3000"

    database_url: str = "sqlite:///./data/contentos.db"
    redis_url: str = "redis://localhost:6379/0"
    spend_limit_usd: float = 25.0

    ai_base_url: str = "https://api.openai.com/v1"
    ai_api_key: str = ""
    ai_model: str = "gpt-4o-mini"

    avatar_engine: str = "simulated"
    heygen_api_key: str = ""
    heygen_api_base: str = "https://api.heygen.com"

    broll_engine: str = "simulated"
    pexels_api_key: str = ""
    higgsfield_api_key: str = ""
    higgsfield_api_base: str = "https://api.higgsfield.ai"

    assembly_engine: str = "simulated"
    shotstack_api_key: str = ""
    shotstack_api_base: str = "https://api.shotstack.io"
    shotstack_env: str = "stage"

    storage_backend: str = "local"
    s3_endpoint_url: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_bucket: str = ""
    s3_region: str = "auto"
    local_storage_dir: str = "./data"

    google_client_id: str = ""
    google_client_secret: str = ""
    youtube_refresh_token: str = ""
    youtube_channel_id: str = ""

    scheduler_interval_seconds: int = 60
    simulated_job_delay_seconds: float = 0.0

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
