"""Tenant registry — the single source of truth for multi-tenancy.

Maps a tenant slug to its sending identity: a default from-address and the set of
domains it is permitted to send from. Both the Lambda handler and the Troposphere
stack read this one registry, so the running code and the provisioned
infrastructure can never drift apart.

Sender-identity resolution here is the anti-spoofing boundary: a resolved sender
must belong to its own tenant's ``from_domains`` or the request is rejected as a
non-retriable failure, so one tenant can never send as another.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Tenant:
    """One tenant's sending identity and the domains it may send from."""

    slug: str
    default_from: str
    from_domains: tuple[str, ...]


class UnknownTenant(Exception):
    """A tenant slug absent from the registry — a non-retriable failure."""

    def __init__(self, slug: str) -> None:
        super().__init__(f"unknown tenant: {slug!r}")
        self.slug = slug


class SenderNotPermitted(Exception):
    """A resolved sender outside the tenant's domains — a non-retriable failure."""

    def __init__(self, address: str, slug: str) -> None:
        super().__init__(f"sender {address!r} is not permitted for tenant {slug!r}")
        self.address = address
        self.slug = slug


# The single source of truth. New tenants are onboarded by adding an entry here;
# the stack provisions their configuration set and the handler resolves them.
TENANTS: dict[str, Tenant] = {
    # Offline demo/test tenant — its domain is intentionally unroutable.
    "acme": Tenant(
        slug="acme",
        default_from="noreply@acme.example",
        from_domains=("acme.example",),
    ),
    "subastae": Tenant(
        slug="subastae",
        default_from="hola@subastae.com",
        from_domains=("subastae.com",),
    ),
}


def resolve_tenant(slug: str) -> Tenant:
    """Return the ``Tenant`` for ``slug`` or raise ``UnknownTenant``."""
    try:
        return TENANTS[slug]
    except KeyError:
        raise UnknownTenant(slug) from None


def configuration_set_name(tenant: Tenant, environment: str) -> str:
    """Derive the SES configuration-set name as ``<slug>-<environment>``."""
    return f"{tenant.slug}-{environment}"


def resolve_sender(tenant: Tenant, from_address: str | None) -> str:
    """Resolve the sender identity, enforcing the tenant's allowed domains.

    Uses ``from_address`` when present, otherwise the tenant's ``default_from``.
    Raises ``SenderNotPermitted`` if the resolved address's domain is not one of
    the tenant's ``from_domains``, preventing cross-tenant spoofing.
    """
    address = from_address or tenant.default_from
    domain = address.rpartition("@")[2].lower()
    if domain not in tenant.from_domains:
        raise SenderNotPermitted(address, tenant.slug)
    return address
