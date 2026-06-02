"""Shared fixtures that keep the test suite offline and hermetic.

These tests must never touch real AWS and must not depend on a developer's local
``notifications/.env`` — which legitimately holds operator config (``ENVIRONMENT``,
``DEPLOY_ARTIFACT_BUCKET``, ``AWS_PROFILE``) for hand-run CLIs. Because
``config.Settings`` declares ``env_file=".env"``, that file would otherwise leak
into ``pytest``: it masks the "missing config" failure paths and, worse, lets
``main()``-level tests fall through ``resolve_config`` into ``run_deploy`` and
execute real ``uv``/``aws`` subprocesses.

The autouse fixture below disables ``.env`` reading and clears the AWS-related
environment variables so every test starts from a clean baseline. Tests that need
a value set it explicitly with ``monkeypatch.setenv``.
"""

import pytest

from notifications import config

# Environment variables read (directly or via ``Settings``) by the engine and its
# CLIs. Cleared before every test so a developer's shell/.env cannot leak in.
_MANAGED_ENV_VARS = (
    "ENVIRONMENT",
    "AWS_REGION",
    "AWS_PROFILE",
    "DEPLOY_ARTIFACT_BUCKET",
    "DELIVERY_DLQ_URL",
)


@pytest.fixture(autouse=True)
def _hermetic_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate every test from any on-disk ``.env`` and inherited AWS env vars."""
    monkeypatch.setattr(
        config.Settings,
        "model_config",
        {**config.Settings.model_config, "env_file": None},
    )
    for name in _MANAGED_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    config.get_settings.cache_clear()
