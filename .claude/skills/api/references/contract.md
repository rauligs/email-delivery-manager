# API Contract Reference

Load this when designing or reviewing routes, OpenAPI, status codes, errors, pagination, webhooks, SSE, WebSockets, idempotency, or versioning.

## Style Selection

* REST resources are the default for public HTTP APIs and CRUD-heavy domains.
* Command endpoints are acceptable for real domain actions, for example `POST /invoices/{id}/void`.
* GraphQL, gRPC, and event streams need explicit reasons: client-driven querying, internal streaming, or strong service-to-service schemas.
* Do not mix styles casually inside one product surface.

## Resource Design

* Model resources around business concepts, not tables.
* Use plural nouns for collections and stable IDs in paths: `/users/{user_id}/sessions`.
* Keep server-generated fields read-only and client-supplied fields explicit.
* Avoid exposing internal flags, persistence-only fields, provider payloads, secrets, and stack traces.

## Datetime & Timezones

* All timestamps in requests, responses, webhook payloads, and cursors are UTC ISO 8601 with explicit offset, for example `2026-05-10T17:42:00Z` or `2026-05-10T17:42:00+00:00`.
* Reject naive datetimes (no offset) at the boundary; do not silently assume UTC.
* Use date-only ISO 8601 (`2026-05-10`) for calendar fields without a time component.
* Durations use ISO 8601 durations (`PT30S`, `P7D`) or an explicit unit-suffixed integer field; do not return ambiguous "seconds vs ms" numbers.
* When a field intentionally carries local time, send it as a naive ISO 8601 value paired with an IANA timezone identifier in a sibling field, for example `{"starts_at_local": "2026-05-10T09:00:00", "timezone": "America/New_York"}`.
* Document precision (seconds vs milliseconds vs microseconds) when it matters for ordering, idempotency windows, or audit reconstruction.

## HTTP Semantics

* `GET`: safe reads only.
* `POST`: create resources or execute commands.
* `PUT`: full replacement.
* `PATCH`: partial update with explicit patch schema.
* `DELETE`: remove, revoke, cancel, or schedule deletion.
* `201` includes the created representation or `Location`.
* `202` means asynchronous work; expose a status resource.
* `204` has no body.
* `400` malformed JSON, invalid request syntax, or invalid query semantics.
* `401` unauthenticated, `403` authenticated but not allowed.
* `404` missing or intentionally hidden resource.
* `409` uniqueness conflict, invalid state transition, duplicate, or idempotency mismatch.
* `413` request body or upload too large.
* `415` unsupported media type.
* `422` Pydantic request validation failure or semantically invalid field combination. This follows FastAPI's default; if a project standardizes on `400` for validation, configure it globally and do not mix both for the same failure class.
* `429` quota or rate limit exceeded.

## Error Envelope

Use one stable envelope across the API. Prefer Problem Details-compatible fields:

```json
{
  "type": "https://api.example.com/problems/validation-error",
  "title": "Validation failed",
  "status": 422,
  "code": "validation_error",
  "detail": "One or more fields are invalid.",
  "instance": "/v1/orders",
  "request_id": "req_01HV...",
  "errors": [
    {"field": "quantity", "code": "greater_than", "message": "Must be greater than 0."}
  ]
}
```

Rules:

* `code` is stable and documented for clients.
* `detail` is safe for users; logs hold the internal exception details.
* Include `request_id` or `correlation_id` on all errors.
* Do not return raw exception strings.

## Pagination

Default to cursor pagination for large or mutable collections:

* Default page size: 50.
* Maximum page size: 100 unless documented otherwise.
* Require deterministic ordering with a unique tie-breaker, usually `created_at DESC, id DESC`.
* Cursor is opaque to clients. Recommended payload before encoding: `{"v":1,"sort":["2026-05-10T12:00:00Z","ord_123"],"dir":"next"}`.
* Keep `limit` as a query parameter and clamp it server-side on every page request.
* Encode with base64url JSON. Sign or server-validate when clients could tamper with sort, tenant, filter, or direction values.
* Include `next_cursor`; include `prev_cursor` only when the endpoint supports reverse traversal correctly.

## Idempotency

Use idempotency keys for side-effect-heavy `POST` operations such as payments, provisioning, exports, email sends, and provider calls. Natural unique constraints, conditional writes, and provider dedupe keys are valid only when they fully prevent duplicate side effects for the operation.

Storage pattern:

* Scope keys by tenant/principal, route, and method.
* Store request hash, processing state, response status, response body or result reference, created time, expiry time, and optional lock owner.
* Expire keys after the business retry window, commonly 24 hours for normal API writes and longer for payment-like workflows.
* Same key and same request returns the stored result.
* Same key and different request returns `409 idempotency_key_reused`.
* In-flight duplicate returns `409`, `202`, or waits briefly, depending on endpoint semantics.

## Versioning & Deprecation

* Additive response fields are usually backward compatible.
* Breaking changes include removing fields, renaming fields, changing meanings, narrowing validation, changing auth semantics, and changing status-code behavior.
* Use URL or media-type versioning for real breaking changes.
* Deprecations need docs, sunset date, migration path, and tests for old and new behavior during overlap.
* FastAPI emits OpenAPI 3.1 in modern versions. If client generators require OpenAPI 3.0, generate or pin a compatible schema in CI and document the compatibility constraint.

## Webhooks

* Use event IDs, event type, creation timestamp, API version, and stable payload schema.
* Sign payloads over timestamp plus raw body; reject old timestamps to reduce replay.
* Delivery is at least once. Consumers must handle duplicates.
* Provide retry schedule, dead-letter visibility, manual replay, and endpoint disablement.

## Streaming, SSE, and WebSockets

Use streaming deliberately; it changes the contract from one response to a long-lived exchange.

SSE and streaming responses:

* Use SSE for one-way server-to-client event streams, especially token streams and progress events.
* Define event names, data shape, terminal event, retry behavior, and heartbeat cadence.
* Handle client disconnects and cancellation so upstream work stops when the client leaves.
* Keep auth and rate limits equivalent to normal HTTP endpoints.
* Avoid buffering the whole stream in memory.
* Account for proxy buffering and idle timeouts in deployment.

WebSockets:

* Use WebSockets only for bidirectional real-time interaction.
* Authenticate during the handshake and re-check authorization for resource-specific messages.
* Define message envelope, message types, error messages, heartbeat/ping behavior, and close codes.
* Apply backpressure, message size limits, connection limits, and idle timeouts.
* Clean up subscriptions, locks, and background tasks on disconnect.
