from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "local"
    log_level: str = "INFO"
    service_name: str = "npm-sentinel-api"
    database_url: str = "postgresql+psycopg://npm_sentinel:npm_sentinel@localhost:5432/npm_sentinel"
    celery_broker_url: str = "amqp://npm_sentinel:npm_sentinel@localhost:5672//"
    celery_result_backend: str | None = None
    npm_registry_base_url: str = "https://registry.npmjs.org"
    npm_registry_timeout_seconds: float = 10.0
    top_packages_source_url: str = (
        "https://raw.githubusercontent.com/Meyond/npm-top-1000-packages/main/README.md"
    )
    top_packages_source_timeout_seconds: float = 10.0
    top_package_limit: int = Field(default=1000, gt=0)
    scheduler_interval_seconds: int = Field(default=300, gt=0)
    scheduler_metadata_concurrency: int = Field(default=10, gt=0)
    scheduler_skip_running_scans: bool = False
    tarball_download_timeout_seconds: float = 30.0
    tarball_max_bytes: int = 50_000_000
    tarball_max_members: int = Field(default=10_000, gt=0)
    tarball_max_uncompressed_bytes: int = Field(default=100_000_000, gt=0)
    tarball_max_file_bytes: int = Field(default=10_000_000, gt=0)
    tarball_max_path_depth: int = Field(default=20, gt=0)
    scanner_max_files: int = Field(default=10_000, gt=0)
    scanner_max_text_file_bytes: int = Field(default=1_000_000, gt=0)
    package_json_max_bytes: int = Field(default=1_000_000, gt=0)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
