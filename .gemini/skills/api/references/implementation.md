# FastAPI Implementation Reference

Load this when implementing Python FastAPI services, Pydantic v2 schemas, pydantic-settings config, async I/O, SQLAlchemy, SQLModel, PgBouncer, Alembic migrations, transactions, outbox, file uploads, background jobs, or lifespan-managed clients.

## Feature Layout

Prefer feature modules for sizable services:

```text
app/
  users/
    router.py
    schemas.py
    service.py
    repository.py
    models.py
    tests/
```

Responsibilities:

* `router.py`: HTTP parsing, dependencies, auth entry points, response model selection.
* `schemas.py`: Pydantic v2 request/response DTOs and serialization rules.
* `service.py`: use-case orchestration, transactions, domain decisions.
* `repository.py`: persistence queries only.
* `models.py`: SQLAlchemy table mapping. SQLModel is an optional SQLAlchemy-based wrapper, not a separate peer architecture.

## FastAPI Rules

* Keep routes thin and typed.
* Use `response_model` or typed response DTOs.
* Use dependency injection for sessions, current principal, authorization context, settings, and external clients.
* Avoid global mutable state except shared clients initialized by lifespan.
* Use Pydantic v2 for request validation and response DTOs.
* Use `pydantic-settings` for config; avoid legacy Pydantic v1 `BaseSettings` imports in new code.
* Prefer SQLAlchemy models as the persistence default. Use SQLModel only when the project already standardizes on it, and still keep API DTOs separate from persistence models.

## Async & I/O

Async is an end-to-end property. Audit the full route-to-provider path:

* Use SQLAlchemy async with `asyncpg`.
* Use `httpx.AsyncClient` for outbound HTTP.
* Use async Redis/Valkey clients in async services.
* Avoid `requests`, sync database drivers, blocking SDK calls, `time.sleep`, large filesystem work, heavy JSON serialization, and CPU-heavy processing on the event loop.
* Wrap unavoidable short sync work in a bounded thread pool or `asyncio.to_thread`.
* Move long-running, CPU-heavy, retryable, or side-effect-heavy work to a worker.
* Monitor event-loop lag and slow callbacks under load.

Timeout default:

* Overall request deadline: 30s unless the endpoint is documented as streaming or long-running.
* HTTP: 5s connect, 10s read, 10s write, 5s pool wait.
* Database statement timeout should be configured for the service or transaction class.
* Lock acquisition should have a short explicit timeout.
* Queue jobs should have execution timeout, retry limit, and dead-letter behavior.
* Propagate remaining request deadlines to downstream calls instead of resetting the timeout budget at every hop.

## Lifespan Pattern

Use lifespan for shared clients and cleanup:

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI
import httpx


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http = httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0))
    try:
        yield
    finally:
        await app.state.http.aclose()


app = FastAPI(lifespan=lifespan)
```

Do not create expensive HTTP clients, database engines, or cache clients per request.

## Persistence

* Put transaction boundaries at the service/use-case level.
* Put integrity in PostgreSQL: foreign keys, unique constraints, checks, exclusions, and `NOT NULL`.
* Add indexes for observed query patterns and verify with query plans.
* Prevent N+1 queries with explicit joins, eager loading, batching, or query redesign.
* Handle concurrency with unique constraints, row locks, optimistic locking, advisory locks, or idempotency keys.
* Keep repositories persistence-focused; do not hide domain decisions inside query helpers.
* If PgBouncer is used in transaction pooling mode, avoid session-level database features and verify asyncpg prepared statement behavior. Disable or configure prepared statement caching unless the deployed PgBouncer and driver configuration explicitly support it.
* Use direct connections or session pooling for workflows that require session state, temporary tables, session advisory locks, or connection-local settings.

## Alembic

* Every schema change uses Alembic and runs in CI.
* Prefer zero-downtime expand/migrate/contract for production changes:
  * expand: add nullable column/table/index or dual-write target.
  * migrate: backfill safely in batches.
  * contract: enforce `NOT NULL`, remove old column, or stop dual-write after deploy overlap.
* Avoid long blocking table rewrites and unbounded backfills in request-time migrations.
* Use concurrent index creation where PostgreSQL and Alembic migration context allow it.

## Outbox Pattern

Use an outbox or equivalent atomic handoff when a database commit must trigger a webhook, queue message, email, provider call, or other external side effect.

Minimum pattern:

* Write the domain change and outbox row in the same transaction.
* A worker reads pending outbox rows, performs the external side effect, and marks rows delivered.
* Workers use idempotent provider keys or dedupe IDs.
* Include retry count, next attempt time, last error, created time, and delivered time.
* Alert on old pending rows and repeated failures.

## Background Jobs

Selection guidance:

* Arq: default for async-native FastAPI services when Redis is acceptable and job needs are straightforward.
* Celery: choose when Beat, Flower, broker flexibility, mature routing, or broad ecosystem support outweigh sync-bridge and operational cost.
* Dramatiq or RQ: use only when existing project conventions and reliability needs fit.
* FastAPI `BackgroundTasks`: use only for short, best-effort same-process work after a response. It is not durable, not a queue, and not suitable for critical, long-running, or retry-heavy work.

Job rules:

* Processors should be idempotent.
* Configure retry limit, backoff, timeout, and dead-letter inspection.
* Include job ID, request ID, tenant/principal where safe, and trace context in logs.
* Return `202 Accepted` plus a status resource when API work continues asynchronously.

## File Uploads & Downloads

* Use `UploadFile` or streaming request handling for large multipart uploads; do not read large files fully into memory.
* Configure body size limits at the application, ASGI server, ingress, and proxy layers.
* Validate filename, content type, detected file type, extension, size, and tenant quota.
* Stream uploads to object storage or temporary files with cleanup.
* Put virus/malware scanning or content safety checks at the boundary required by the product risk.
* Stream large downloads with range support where useful; set safe `Content-Disposition` and cache headers.
