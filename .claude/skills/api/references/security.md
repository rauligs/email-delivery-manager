# API Security Reference

Load this when implementing or reviewing authentication, authorization, tenant isolation, secrets, CORS, transport security, password hashing, rate limiting, OWASP API risks, or data privacy.

## Baseline Risks

Treat OWASP API risks as the minimum review lens:

* Broken object-level authorization.
* Weak authentication.
* Broken object property-level authorization and excessive data exposure.
* Unrestricted resource consumption.
* Broken function-level authorization.
* Mass assignment.
* Security misconfiguration.
* Injection.
* API inventory gaps.
* Unsafe consumption of third-party APIs.

## Authentication

* Prefer OAuth2/OIDC for user-facing products.
* Public clients use authorization code with PKCE.
* Machine clients use scoped credentials or client credentials flow.
* Validate JWT issuer, audience, signature, algorithm, expiry, not-before, and key ID.
* Support key rotation and reject unknown or weak signing algorithms.
* Use short-lived access tokens. Refresh tokens require rotation, replay detection, revocation, and secure storage.
* If the service owns passwords, hash with Argon2id by default. Bcrypt is acceptable when Argon2id is unavailable or not approved. Do not use MD5, SHA-1, unsalted hashes, reversible encryption, or low-cost PBKDF2.

## Authorization

Enforce authorization in layers:

* Authenticated principal.
* Capability, role, policy, or relationship check.
* Tenant/org/account boundary.
* Object-level authorization on the specific resource.

Rules:

* Repository queries should be tenant-scoped when resources are tenant-scoped.
* Tests must prove cross-tenant access fails.
* Admin paths need explicit function-level authorization, not only hidden UI controls.
* Do not infer authorization from client-supplied IDs without server-side ownership checks.

## Input & Output Safety

* Use explicit Pydantic request schemas; avoid mass assignment.
* Constrain lengths, ranges, enum values, content types, file sizes, array sizes, and query complexity.
* Default caps: request body 10 MB, JSON depth 64, array length 1000. File upload caps are project-specific but must be enforced at the app or edge and documented in OpenAPI.
* Use allowlists for sort fields, filter fields, redirect URLs, and external callback targets.
* Never expose secrets, tokens, password hashes, internal policy details, provider raw errors, stack traces, or hidden fields in responses.
* Use parameterized SQL and ORM expression APIs; never concatenate untrusted SQL fragments.

## Rate Limits & Quotas

Apply limits by the dimension that matches abuse risk:

* Principal for normal authenticated actions.
* Tenant/account for shared resource protection.
* IP or network for unauthenticated endpoints.
* Token/client ID for machine clients.
* Route-specific limits for expensive or sensitive endpoints.

Return `429` with a stable error `code` and retry metadata when available.

## CORS & Browser Exposure

* Keep allowed origins narrow.
* Do not use wildcard origins with credentials.
* Restrict methods and headers to what the client needs.
* CSRF protection is required for cookie-authenticated browser writes.

## Transport Security

* Enforce trusted TLS in production, either at the app edge, trusted ingress, service mesh, or documented internal transport layer.
* Use HSTS for browser-facing APIs once HTTPS is stable for the domain.
* Set `Secure`, `HttpOnly`, and appropriate `SameSite` attributes when cookies are used.
* Trust `X-Forwarded-Proto`, `Forwarded`, client IP, and host headers only from known proxies or ingress.
* Redirect or reject plaintext HTTP at the edge or application boundary.

## Secrets & Configuration

* Load config through `pydantic-settings` or the project's approved secret manager.
* Do not commit `.env` files, credentials, private keys, or provider tokens.
* Validate required config at startup.
* Redact secrets from logs, traces, errors, metrics labels, and audit events.
* Document secret owners, rotation cadence, revocation procedure, and emergency rotation steps.
* Rotate credentials after suspected exposure, personnel/provider changes, privilege changes, or at the project's required interval.

## Privacy & Governance

* Classify data by sensitivity and apply least privilege in code, database roles, support tools, analytics exports, and logs.
* Minimize collected fields and response payloads.
* Define retention, deletion, anonymization, and export behavior for user, tenant, audit, and operational data.
* Treat analytics exports and warehouse syncs as governed data interfaces.
* Mask or tokenize sensitive values where full fidelity is not required.
* Test compliance-relevant behavior when applicable: consent, deletion, retention, audit trails, and regional data boundaries.

## Audit Events

Record security-relevant actions separately from diagnostic logs:

* Login, logout, token refresh, token revocation.
* Permission, role, team, tenant, or admin changes.
* Data exports, destructive writes, and privileged reads.
* Webhook endpoint changes and credential rotations.

Audit records should include actor, action, target, timestamp, request ID, tenant/account, outcome, and safe metadata.
