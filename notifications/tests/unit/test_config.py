import pytest
from pydantic import ValidationError

from notifications.config import Settings, get_settings


def test_environment_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_defaults_when_only_environment_is_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    monkeypatch.delenv("DELIVERY_DLQ_URL", raising=False)

    settings = Settings(_env_file=None)

    assert settings.environment == "test"
    assert settings.aws_region == "eu-central-1"
    assert settings.aws_profile is None
    assert settings.delivery_dlq_url is None


def test_reads_all_values_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "prod")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("AWS_PROFILE", "sso-prod")
    monkeypatch.setenv("DELIVERY_DLQ_URL", "https://sqs.example/dlq")

    settings = Settings(_env_file=None)

    assert settings.environment == "prod"
    assert settings.aws_region == "us-east-1"
    assert settings.aws_profile == "sso-prod"
    assert settings.delivery_dlq_url == "https://sqs.example/dlq"


def test_get_settings_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()

    first = get_settings()
    second = get_settings()

    assert first is second
