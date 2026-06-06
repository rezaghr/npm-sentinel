import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_scheduler_defaults_are_valid() -> None:
    settings = Settings()
    assert settings.top_package_limit > 0
    assert settings.scheduler_interval_seconds > 0
    assert settings.scheduler_metadata_concurrency > 0
    assert settings.scheduler_skip_running_scans is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("TOP_PACKAGE_LIMIT", "0"),
        ("SCHEDULER_INTERVAL_SECONDS", "0"),
        ("SCHEDULER_METADATA_CONCURRENCY", "0"),
    ],
)
def test_scheduler_positive_config_validation(field: str, value: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(field, value)
    with pytest.raises(ValidationError):
        Settings()
