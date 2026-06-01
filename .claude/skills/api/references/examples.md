# API Examples Reference

Load this when the implementation needs canonical shapes instead of prose guidance.

## Error Envelope

```json
{
  "type": "https://api.example.com/problems/resource-conflict",
  "title": "Resource conflict",
  "status": 409,
  "code": "order_already_submitted",
  "detail": "The order has already been submitted.",
  "instance": "/v1/orders/ord_123/submit",
  "request_id": "req_01HV9ZKQ7E8E9W4E6R2P3N4M5A"
}
```

Validation variant:

```json
{
  "type": "https://api.example.com/problems/validation-error",
  "title": "Validation failed",
  "status": 422,
  "code": "validation_error",
  "detail": "One or more fields are invalid.",
  "instance": "/v1/orders",
  "request_id": "req_01HV9ZKQ7E8E9W4E6R2P3N4M5A",
  "errors": [
    {"field": "items.0.quantity", "code": "greater_than", "message": "Must be greater than 0."}
  ]
}
```

## Cursor Payload

The client receives only an opaque encoded string. The decoded server payload can look like:

```json
{
  "v": 1,
  "sort": ["2026-05-10T12:00:00Z", "ord_123"],
  "dir": "next"
}
```

Recommended query ordering:

```sql
ORDER BY created_at DESC, id DESC
```

Use a unique tie-breaker. Keep `limit` as a query parameter clamped server-side on every request. Sign or server-validate cursor values if clients could modify tenant, filters, sort, or direction.

## Feature Module Layout

```text
app/
  orders/
    router.py
    schemas.py
    service.py
    repository.py
    models.py
    tests/
      test_orders_api.py
      test_orders_service.py
```

Shape:

* Router owns HTTP concerns.
* Service owns transaction and use-case flow.
* Repository owns SQL.
* Schemas own API DTOs.
* Models own persistence mapping.

## FastAPI Lifespan

```python
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http = httpx.AsyncClient(
        timeout=httpx.Timeout(
            timeout=10.0,
            connect=5.0,
            read=10.0,
            write=10.0,
            pool=5.0,
        )
    )
    try:
        yield
    finally:
        await app.state.http.aclose()


app = FastAPI(lifespan=lifespan)
```

## SSE Streaming

```python
import asyncio
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

router = APIRouter()


async def event_stream(request: Request) -> AsyncIterator[str]:
    while not await request.is_disconnected():
        yield "event: heartbeat\ndata: {}\n\n"
        await asyncio.sleep(15)


@router.get("/runs/{run_id}/events")
async def stream_run_events(run_id: str, request: Request) -> StreamingResponse:
    return StreamingResponse(event_stream(request), media_type="text/event-stream")
```

Production streams should define event names, terminal event, heartbeat cadence, auth rules, rate limits, and cancellation behavior.

## WebSocket Shape

```python
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


@router.websocket("/ws/runs/{run_id}")
async def run_socket(websocket: WebSocket, run_id: str) -> None:
    # Authenticate and authorize from headers/cookies/query token before accept
    # when possible; close with policy violation for unauthorized clients.
    await websocket.accept()
    try:
        while True:
            message = await websocket.receive_json()
            # Validate message type, authorize the run, apply size/rate limits, then handle.
            await websocket.send_json({"type": "ack", "id": message.get("id")})
    except WebSocketDisconnect:
        # Clean up subscriptions, locks, and background work for this connection.
        return
```

## Idempotency Table

```sql
CREATE TABLE api_idempotency_keys (
    tenant_id text NOT NULL,
    principal_id text NOT NULL,
    method text NOT NULL,
    route text NOT NULL,
    key text NOT NULL,
    request_hash text NOT NULL,
    status text NOT NULL,
    response_status integer,
    response_body jsonb,
    result_ref text,
    locked_until timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    PRIMARY KEY (tenant_id, principal_id, method, route, key)
);
```

Behavior:

* Insert `processing` row before executing the side effect.
* Same key and same hash returns stored response when complete.
* Same key and different hash returns `409 idempotency_key_reused`.
* Expire rows after the documented retry window.

## Outbox Table

```sql
CREATE TABLE outbox_events (
    id bigserial PRIMARY KEY,
    event_type text NOT NULL,
    aggregate_type text NOT NULL,
    aggregate_id text NOT NULL,
    payload jsonb NOT NULL,
    status text NOT NULL DEFAULT 'pending',
    attempts integer NOT NULL DEFAULT 0,
    next_attempt_at timestamptz NOT NULL DEFAULT now(),
    last_error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    delivered_at timestamptz
);

CREATE INDEX outbox_events_pending_idx
ON outbox_events (next_attempt_at, id)
WHERE status = 'pending';
```

Write the domain row and outbox row in the same transaction. A worker claims pending rows, performs the side effect with a dedupe key, and marks delivery.

## File Upload Boundary

```python
from fastapi import APIRouter, File, HTTPException, UploadFile, status

router = APIRouter()


@router.post("/documents")
async def upload_document(file: UploadFile = File(...)) -> dict[str, str]:
    if file.content_type not in {"application/pdf"}:
        # Assumes a global exception handler maps this to the standard error envelope.
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="unsupported_media_type",
        )

    # Stream chunks to object storage or a temp file; do not read large files at once.
    while chunk := await file.read(1024 * 1024):
        pass

    return {"status": "accepted"}
```

Real handlers should enforce size limits before and during reads, clean temporary files, scan when required, and return the standard error envelope instead of ad hoc errors.

## Expand/Contract Migration

Expand migration:

```python
def upgrade() -> None:
    op.add_column("users", sa.Column("display_name", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "display_name")
```

Backfill outside the request path in batches:

```sql
WITH batch AS (
    SELECT id
    FROM users
    WHERE display_name IS NULL
    ORDER BY id
    LIMIT 1000
)
UPDATE users
SET display_name = users.full_name
FROM batch
WHERE users.id = batch.id;
```

Contract migration after code reads/writes the new field and data is complete:

```python
def upgrade() -> None:
    op.alter_column("users", "display_name", nullable=False)
```
