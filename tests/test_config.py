from app.core.config import Settings


def test_default_settings_load() -> None:
    settings = Settings()

    assert settings.service_name == "npm-sentinel-api"
    assert settings.database_url.startswith("postgresql+psycopg://")
    assert settings.celery_broker_url.startswith("amqp://")
    assert settings.celery_result_backend is None
    assert settings.top_package_limit == 1000
    assert settings.scheduler_interval_seconds == 300
    assert settings.scheduler_metadata_concurrency == 10
