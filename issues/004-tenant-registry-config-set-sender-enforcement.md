# Tenant registry, derived configuration set, and sender-identity enforcement

**Priority tier:** Tracer Bullet

PRD US-2 and the CONTEXT.md invariants. The backbone of multi-tenancy: one registry read by
both the handler and the infrastructure, with anti-spoofing enforced.

## Acceptance criteria

- Typed registry at `src/notifications/tenants.py` mapping slug → `Tenant(slug, default_from,
  from_domains)`, as the single source of truth.
- The handler resolves the Tenant from the validated `tenant` field; an unknown tenant is a
  **non-retriable** outcome.
- The SES configuration set name is **derived** as `<slug>-<environment>` (environment from an
  env var such as `ENVIRONMENT`) and passed to SES as `ConfigurationSetName`.
- Sender identity resolution: use the payload `from_address` if present, otherwise the
  Tenant's `default_from`. The resolved address MUST belong to the Tenant's `from_domains`,
  or the request is rejected as **non-retriable** (no cross-Tenant spoofing).
- The Troposphere stack loops the registry to create one SES configuration set per Tenant; an
  offline synth test asserts one per tenant with the derived name.
- Tests cover: resolution, default fallback, unknown-tenant rejection, and
  from_address-outside-domains rejection.
- `./scripts/verify.sh` passes.

## Dependencies

- 002, 003
