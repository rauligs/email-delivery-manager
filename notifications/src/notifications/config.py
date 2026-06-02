"""Typed settings for the notification engine.

`Settings` is the single reader of environment variables for this module. Other
code should depend on `get_settings()` (or accept a `Settings` instance) rather
than reading `os.environ` directly.

Optional `.env` support is for local CLI use only and must hold non-secret
operator config (for example `AWS_PROFILE`). `.env` is gitignored; secrets are
injected by the deployed stack at runtime, never committed.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Required at runtime; deployment targets such as "staging" or "prod".
    environment: str

    # Default deployment region; override per environment when needed.
    aws_region: str = "eu-central-1"

    # Optional named profile for local AWS SSO sessions.
    aws_profile: str | None = None

    # S3 bucket the deploy CLI uploads the packaged Lambda artifact to before
    # CloudFormation references it. Used only by the out-of-loop deploy tool.
    deploy_artifact_bucket: str | None = None

    # SQS dead-letter queue URL injected by the stack at runtime.
    delivery_dlq_url: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
