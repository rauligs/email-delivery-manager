# Operations & Testing Reference

Load this when reviewing OpenTelemetry, reliability, observability, deadline propagation, health probes, performance, deployment, CI, test strategy, or production readiness.

## Reliability

Use distinct probe semantics:

* Liveness, commonly `/livez`: process is alive and should not be restarted.
* Readiness, commonly `/readyz`: service can receive traffic; include critical dependencies needed for normal request handling.
* Startup, commonly `/startupz`: slow bootstrapping has finished; useful when the platform supports startup probes.

* Use graceful shutdown to drain in-flight requests and stop accepting new work.
* Retry only bounded, retryable failures with exponential backoff and jitter.
* Do not retry non-idempotent operations unless protected by idempotency keys or duplicate detection.
* Default request deadline is 30s unless the endpoint is documented as streaming or long-running. Propagate deadlines across downstream calls; each hop should use the remaining budget, not a fresh full timeout.
* Add circuit breakers or load shedding when upstream failures can cascade.
* Document degraded behavior for optional dependencies.

## Observability

Structured logs should include:

* timestamp, level, service, environment.
* route template, method, status, latency.
* request ID and trace ID.
* safe tenant/principal identifiers when useful.
* error code and exception class for failures.

Metrics should include:

* request count, latency, and error rate by route/status class.
* database pool usage and query latency.
* outbound provider latency/error rate.
* queue depth, job latency, retry count, and dead-letter count.
* cache hit rate and cache errors.
* event-loop lag for async services.

Use OpenTelemetry for tracing and, where the project supports it, metrics and log correlation. Traces should propagate across inbound requests, outbound calls, database, cache, queues, and jobs.

Alerts should target user-visible symptoms: high error rate, high p95/p99 latency, saturation, queue lag, failed jobs, and dependency failure.

## Performance

* Set a latency and throughput goal before tuning critical endpoints.
* Limit body size, response size, page size, file size, and expensive query shapes.
* Stream large uploads/downloads instead of buffering whole payloads.
* Test streaming responses, SSE, and WebSockets under disconnects, slow clients, and backpressure.
* Cache deterministic expensive reads only when invalidation is clear.
* Use `ETag`, `Last-Modified`, `Cache-Control`, compression, and CDN behavior intentionally.
* Load-test critical endpoints and inspect p95/p99 latency, database time, queue lag, memory, CPU, and saturation.

## Testing

Minimum useful coverage:

* Unit tests for domain services and authorization rules without HTTP when possible.
* Integration tests with `httpx.AsyncClient` and FastAPI lifespan support.
* Real PostgreSQL tests for persistence behavior, commonly via Testcontainers or CI service containers.
* Migration tests for forward migration and rollback/roll-forward behavior where practical.
* Contract tests or OpenAPI snapshot checks for public APIs.
* Authn/authz matrix tests, including cross-tenant denial.
* Validation failures, conflict cases, pagination boundaries, idempotency behavior, and error envelope tests.
* External provider boundary tests using fakes, sandboxes, or contract tests for high-risk integrations.

## CI Gates

Use the gates supported by the project:

* test suite.
* lint and format check.
* type check.
* migration check.
* OpenAPI compatibility check.
* dependency vulnerability scan.
* container build.
* smoke test or health check after deploy.

## Delivery

* Build immutable containers with pinned dependencies and reproducible builds.
* Run production with a real ASGI server/process manager configuration; never use reload mode.
* Validate config at startup.
* Deploy risky changes behind feature flags where useful.
* Coordinate migrations with application deploy order.
* Keep rollback or roll-forward paths clear.
* Back up databases and verify restores on a schedule.

## Hardening

* Use minimal container images.
* Run as a non-root user.
* Prefer read-only filesystems where practical.
* Set CPU/memory requests and limits.
* Configure ingress timeout, body size, and rate limit policies.
* Avoid secrets in environment dumps, process args, logs, and crash reports.
