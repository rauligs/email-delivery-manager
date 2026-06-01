# Validate the Delivery request payload (Pydantic v2)

**Priority tier:** Tracer Bullet

PRD US-3. Turn raw SQS message bodies into a validated Delivery request, with invalid
payloads classified as non-retriable.

## Acceptance criteria

- A Pydantic v2 model validates each Delivery request:
  - required: `tenant`, `template_name`, `to`, `subject`;
  - optional: `from_name`, `from_address`, `template_data` (arbitrary object).
  - `to` is a single recipient and must be a valid email address.
- Schema-invalid payloads are surfaced as a **non-retriable** outcome (a typed
  error/result the handler can branch on), not raised as a transient failure.
- The handler parses each record through the model before any rendering/sending.
- Tests cover a valid payload and representative invalid ones (missing required field,
  malformed email, wrong types, non-JSON body).
- `./scripts/verify.sh` passes.

## Dependencies

- 002
