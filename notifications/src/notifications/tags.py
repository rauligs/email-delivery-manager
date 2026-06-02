"""Standard AWS resource tags for the notification engine.

Every AWS resource the stack creates carries the same baseline tag set so
resources can be attributed, filtered, and cleaned up by environment.
"""


def standard_tags(environment: str) -> dict[str, str]:
    """Return the tag set applied to every AWS resource for ``environment``."""
    return {
        "app": "notification-engine",
        "environment": environment,
        "managed-by": "email-delivery-manager",
    }
