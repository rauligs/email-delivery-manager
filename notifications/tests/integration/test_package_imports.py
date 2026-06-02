"""Integration placeholder: confirms the package and its public helpers import.

Real cross-component integration tests (render + send, deploy) arrive in later
issues. This keeps the integration suite wired into verification from issue 001.
"""

import notifications
from notifications.config import get_settings
from notifications.tags import standard_tags


def test_package_exposes_a_version() -> None:
    assert isinstance(notifications.__version__, str)
    assert notifications.__version__


def test_public_helpers_are_callable() -> None:
    assert callable(get_settings)
    assert callable(standard_tags)
