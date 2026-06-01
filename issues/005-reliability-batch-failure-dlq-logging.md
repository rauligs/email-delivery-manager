# Reliability — partial-batch-failure, error classification, DLQ, and structured logging

**Priority tier:** Tracer Bullet

PRD US-4 and US-9. Make at-least-once delivery safe: retry only what should be retried, park
the rest, and log every outcome without leaking data.

## Acceptance criteria

- The handler returns an SQS partial batch response whose `batchItemFailures` contains **only**
  records that hit **transient** errors (SES throttling/5xx, network/timeouts).
- **Non-retriable** errors (validation, unknown tenant, missing template, sender-domain
  violation) are logged with context and the offending message is **explicitly forwarded to
  the DLQ** (`sqs:SendMessage`), then treated as handled (NOT in `batchItemFailures`) so it
  leaves the source queue without burning retries.
- Troposphere stack additions:
  - DLQ with a redrive policy of `maxReceiveCount = 3` on the delivery queue;
  - event-source mapping with `FunctionResponseTypes = [ReportBatchItemFailures]`, a batch
    size/window, and a conservative, configurable `ScalingConfig.MaximumConcurrency`;
  - IAM scoped to: `ses:SendEmail` for the tenants' configuration sets, receive/delete on the
    source queue, `sqs:SendMessage` to the DLQ, and CloudWatch Logs.
- Structured JSON logging: one line per record with `tenant`, `template_name`, SQS message id,
  SES message id, outcome, and error class. `template_data` contents are never logged; the
  recipient is redacted to its domain.
- Tests: a mixed batch (success + transient + non-retriable) produces the correct
  `batchItemFailures` and a DLQ forward for the non-retriable record; log shape + redaction are
  asserted; an offline synth test asserts the DLQ/redrive, ESM settings, and IAM scoping.
- `./scripts/verify.sh` passes.

## Dependencies

- 002, 003, 004
