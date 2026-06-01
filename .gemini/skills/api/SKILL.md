---
name: Production API Development
description: Use when building or reviewing Python FastAPI services, REST API contracts, Pydantic v2 schemas, pydantic-settings config, async SQLAlchemy, SQLModel, Alembic migrations, OpenAPI specs, SSE/WebSockets, streaming uploads, authentication, authorization, idempotency, pagination, OpenTelemetry, PgBouncer, outbox patterns, deployment, or OWASP API hardening.
---

# Production API Development

Use this single skill for production Python HTTP API work. Keep `SKILL.md` as the entry point; load the internal references below only when the task touches that area.

## Topic Index

* Contract, OpenAPI, status codes, errors, pagination, idempotency, webhooks, SSE, WebSockets: [references/contract.md](references/contract.md).
* FastAPI, Pydantic v2, pydantic-settings, async I/O, SQLAlchemy, SQLModel, PgBouncer, Alembic, outbox, uploads, workers, lifespan: [references/implementation.md](references/implementation.md).
* OWASP API risks, authn/authz, tenants, CORS, rate limits, HTTPS, password hashing, secrets, privacy: [references/security.md](references/security.md).
* OpenTelemetry, logs, metrics, traces, probes, deadlines, performance, CI, deployment, tests: [references/operations-testing.md](references/operations-testing.md).
* Canonical snippets for error envelopes, cursors, feature layout, lifespan, SSE/WebSocket, idempotency, outbox, uploads, migrations: [references/examples.md](references/examples.md).

## MUST Rules

* Route handlers must stay thin: validate input, authorize, call services, and return typed responses.
* Domain logic must be testable without FastAPI request objects, HTTP context, or global mutable state.
* Response models must be explicit DTOs, not ORM models.
* Public behavior must be contract-visible: status codes, error envelope, auth requirements, pagination, idempotency, and side effects appear in OpenAPI or docs.
* Never return raw exception messages, stack traces, SQL errors, tokens, secrets, provider internals, or policy internals to clients.
* Never perform blocking I/O or CPU-heavy work on the async event loop. Audit the full route-to-provider call path.
* Every outbound network call, database operation, lock acquisition, queue operation, and background job must have an explicit timeout/deadline.
* Request deadlines must propagate across downstream calls; retries must not exceed the remaining request budget.
* Retried writes must use a named duplicate-control strategy: idempotency key, natural unique constraint, conditional write, provider dedupe key, or documented replay-safe operation.
* Database commits coupled to external side effects must use an outbox pattern or an equivalent atomic handoff.
* Authorization must include object-level and tenant-level checks wherever resources are user-, account-, org-, or tenant-scoped.
* Request body size, file size, JSON depth, array length, and query complexity must have explicit caps at the app or edge; default body cap is 10 MB, JSON depth cap is 64, array length cap is 1000, and upload caps are project-specific but documented in OpenAPI.
* All APIs, including internal services, must be reviewed against OWASP API risks; see [references/security.md](references/security.md) for the control checklist.
* Database schema changes must use reviewed Alembic migrations and preserve production rollout safety.
* Logs, traces, metrics, and audit events must redact secrets and sensitive data.
* Production APIs must enforce trusted TLS or an explicitly documented internal transport policy, trust forwarded headers only from known proxies, and redirect or reject plaintext. Browser-facing APIs must also set secure cookie attributes when cookies are used and enable HSTS at the edge.

## SHOULD Defaults

* Prefer REST-style HTTP resources for public CRUD-heavy APIs; use command endpoints only for domain actions that are not resource replacement.
* Prefer cursor pagination for large or mutable collections. Default page limit is 50; maximum is 100 unless the endpoint documents a different bound.
* Use an opaque cursor containing version, sort values, and direction; keep `limit` as a query parameter clamped server-side on every request.
* Use one Problem Details-style error envelope with stable application `code` values and a request/correlation ID.
* Use FastAPI's default `422` for Pydantic validation and semantically invalid field combinations, `400` for malformed syntax, `409` for uniqueness conflicts or invalid state transitions, `401` for unauthenticated, `403` for forbidden, and `404` for missing or intentionally hidden resources.
* Default request deadline is 30s. Default outbound HTTP timeout budget is 5s connect, 10s read, 10s write, 5s pool wait within the remaining deadline.
* Use SQLAlchemy async with `asyncpg`, `httpx.AsyncClient`, and async Redis/Valkey clients for async services.
* Use Pydantic v2 with `pydantic-settings` for configuration; avoid legacy Pydantic v1 `BaseSettings` imports.
* Use lifespan hooks for shared clients and pools. Do not create expensive clients per request.
* Use Alembic expand/migrate/contract phases for risky production schema changes.
* Use Arq for async-native FastAPI jobs by default; choose Celery when Beat, Flower, broker flexibility, or ecosystem maturity outweigh sync-bridge cost.
* Emit structured JSON logs with route, method, status, latency, request ID, trace ID, and safe tenant/principal identifiers; use OpenTelemetry for traces.
* Test the authz matrix, validation failures, conflict cases, pagination boundaries, idempotency behavior, migrations, and error envelope.
* Run tests, linting, typing, migration checks, dependency scans, container build checks, and OpenAPI compatibility checks in CI when the project supports them.

## MAY Choices

* Use GraphQL only when client-driven querying is a real requirement and the team can manage its security, caching, complexity, and observability tradeoffs.
* Use gRPC or event streams for internal service-to-service workflows needing strong schemas, streaming, or low latency.
* Use `asyncio.to_thread` for short unavoidable blocking work; use workers for long-running, CPU-heavy, retryable, or side-effect-heavy work.
* Use offset pagination only for small, stable datasets with deterministic ordering.

## Workflow

1. Survey existing project patterns while identifying the contract surface: resource, method, request, response, status codes, errors, auth, pagination, idempotency, and side effects.
2. Check the relevant reference file before implementing risky or detailed behavior.
3. Match existing project patterns when they satisfy the MUST rules; otherwise state the gap and make the smallest production-safe correction.
4. Add or update tests at the lowest useful level, then cover public API behavior through integration or contract tests.
5. Verify observability and failure behavior, then run the MUST Verification Pass before considering the change done.

## MUST Verification Pass

* Verify each MUST rule applies or has an explicit, local rationale for why it does not.
* Grep for sibling endpoints/modules and match established safe patterns where they satisfy this skill.
* Run the relevant tests, linting, typing, migration checks, OpenAPI compatibility checks, and dependency scans supported by the project.
* Exercise rollout, rollback, deprecation, or compatibility paths when the change touches contracts, migrations, auth, queues, or clients.
* Smoke-test the changed API path locally or in staging with representative success, failure, and auth cases.
