"""The tenant registry is the single source of truth for multi-tenancy.

Covers Tenant resolution, the derived SES configuration-set name, sender-identity
resolution with the default fallback, and the two non-retriable rejections:
an unknown tenant and a resolved sender outside the tenant's allowed domains.
"""

import pytest

from notifications.tenants import (
    TENANTS,
    SenderNotPermitted,
    Tenant,
    UnknownTenant,
    configuration_set_name,
    resolve_sender,
    resolve_tenant,
)


def test_registry_is_keyed_by_slug() -> None:
    for slug, tenant in TENANTS.items():
        assert isinstance(tenant, Tenant)
        assert tenant.slug == slug


def test_resolve_tenant_returns_the_registered_tenant() -> None:
    tenant = resolve_tenant("acme")

    assert tenant.slug == "acme"
    assert tenant.default_from
    assert tenant.from_domains


def test_unknown_tenant_is_rejected() -> None:
    with pytest.raises(UnknownTenant):
        resolve_tenant("nope")


def test_configuration_set_name_is_derived_from_slug_and_environment() -> None:
    tenant = resolve_tenant("acme")

    assert configuration_set_name(tenant, "prod") == "acme-prod"
    assert configuration_set_name(tenant, "staging") == "acme-staging"


def test_resolve_sender_uses_the_payload_from_address_when_in_domain() -> None:
    tenant = resolve_tenant("acme")

    assert resolve_sender(tenant, "reports@acme.example") == "reports@acme.example"


def test_resolve_sender_falls_back_to_the_tenant_default() -> None:
    tenant = resolve_tenant("acme")

    assert resolve_sender(tenant, None) == tenant.default_from


def test_resolve_sender_rejects_an_address_outside_the_tenant_domains() -> None:
    tenant = resolve_tenant("acme")

    with pytest.raises(SenderNotPermitted):
        resolve_sender(tenant, "noreply@evil.example")


def test_the_tenant_default_belongs_to_its_own_domains() -> None:
    for tenant in TENANTS.values():
        assert resolve_sender(tenant, None) == tenant.default_from
