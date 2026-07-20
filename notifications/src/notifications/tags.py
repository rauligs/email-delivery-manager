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


def tenant_tags(environment: str, tenant_slug: str) -> dict[str, str]:
    """Return the standard tags plus the owning tenant.

    Applied to per-tenant resources (SES identity, configuration set) so one
    tenant's footprint is filterable in a shared AWS account.
    """
    return standard_tags(environment) | {"tenant": tenant_slug}
