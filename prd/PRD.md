# PRD — Multi-Tenant Serverless Notification Engine

> Design record this PRD is built on: [CONTEXT.md](../CONTEXT.md),
> [docs/adr/0001](../docs/adr/0001-serverless-ses-notification-engine.md),
> [TENANT-ONBOARDING.md](../TENANT-ONBOARDING.md).

## Problem Statement

The operator runs several private projects, each of which needs to send templated
transactional and notification emails (welcome, weekly report, receipts, alerts). There is
no shared, reliable way to do this today. Each project re-solving email is wasteful, and
ad-hoc sending gives no separation of per-project bounce/complaint metrics, no consistent
templating, and no decoupling between "a thing happened" and "an email went out."

The team needs **one** engine that:

- serves multiple distinct sending products (**Tenants**) from a single deployment;
- decouples producers from delivery (a producer enqueues a request and moves on);
- renders per-Tenant HTML templates with per-request data, including list/table loops;
- sends via Amazon SES with per-Tenant metric separation and no cross-Tenant sender spoofing;
- is cheap, serverless, and fully operable through this repo's existing Ralph AFK workflow —
  meaning it must be **authored and verified entirely offline**, with no real AWS in the loop.

## Proposed Solution

A new `notifications/` Python module implementing an asynchronous **SQS → Lambda → SES**
pipeline.

- **Producers** (the operator's projects) enqueue a JSON **Delivery request** onto an SQS
  queue. They never call SES directly.
- A **Lambda** consumes SQS batches and, per message: validates the payload, looks up the
  **Tenant** in an in-repo registry, resolves and enforces the **Sender identity**, loads the
  named **Template** from the embedded filesystem, renders it with `template_data` (Jinja2),
  and calls SES `SendEmail` under the Tenant's configuration set (`<slug>-<environment>`).
- **Infrastructure** (delivery queue + DLQ, Lambda + event-source mapping, least-privilege
  IAM, one SES configuration set per Tenant) is authored in **Troposphere**, synthesized to
  CloudFormation, and asserted on in `pytest` — 100% offline. Real deploys are a manual
  `aws cloudformation deploy` outside the loop.
- **Three operator CLIs** (`deploy`, `tenant-setup`, `smoke-test`) cover real-AWS operations.
  They hit AWS only when run by hand; in tests their boto3 calls are mocked.
- **Repo adaptation:** `scripts/verify.sh` gains a `notifications` project; `CLAUDE.md` gains
  a `notifications/ → python skill` routing line. The existing `api/`/`background/`/`web/`/
  `shared/` scaffold stays dormant.

Default region: **`eu-central-1`** (Frankfurt).

## User Stories (Definition of Done)

Stories are vertical slices; the walking skeleton (US-1) is the tracer bullet.

### US-1 — Render and send one email end-to-end (tracer bullet)
As an integrating project, when I enqueue a valid Delivery request for a known Tenant and
template, the engine renders it and sends it via SES.
**DoD:** handler parses an SQS event; loads `templates/<tenant>/<name>.html`; renders with
Jinja2 (including a `{% for %}` table loop); builds the SES request (From/To/Subject/HTML
body); calls a SES client that is **stubbed in tests**. A minimal Troposphere stack synthesizes
the queue + Lambda + role. Unit tests assert the rendered HTML and the SES call arguments.

### US-2 — Tenant registry, derived configuration set, sender enforcement
**DoD:** typed registry at `notifications/src/notifications/tenants.py` (slug, default_from,
from_domains). Handler resolves the Tenant from the `tenant` field; computes the configuration
set name `<slug>-<environment>` and passes it to SES; resolves the Sender identity (payload
`from_address` else `default_from`); **rejects** a `from_address` outside the Tenant's
`from_domains` as non-retriable. Unknown Tenant → non-retriable. Tests cover resolution,
default fallback, and both rejections.

### US-3 — Payload validation
**DoD:** a Pydantic v2 model validates each Delivery request (required: `tenant`,
`template_name`, `to`, `subject`; optional: `from_name`, `from_address`, `template_data`).
Schema-invalid payloads are classified non-retriable. Tests cover valid and invalid payloads.

### US-4 — Reliability: partial-batch-failure, error classification, DLQ
**DoD:** handler returns `batchItemFailures` containing **only** the messages that hit
**transient** errors (SES throttling/5xx, network); SQS retries just those, DLQ after
`maxReceiveCount = 3`. **Non-retriable** errors (validation, unknown Tenant, missing template,
sender-domain violation) are logged with context and **forwarded to the DLQ explicitly**, then
treated as handled (not reported as failures) so they are removed from the source queue
without burning retries. Tests cover a mixed batch and each classification.

### US-5 — Troposphere infrastructure, verified by offline synthesis
**DoD:** `infra/stack.py` builds the delivery queue + DLQ (redrive, `maxReceiveCount=3`),
Lambda (python3.12) with an event-source mapping (batching, `ReportBatchItemFailures`,
`maximum_concurrency`), a least-privilege IAM role (`ses:SendEmail` scoped to the Tenants'
configuration sets, SQS receive/delete on source, `sqs:SendMessage` on DLQ, CloudWatch logs),
and **one SES configuration set per Tenant** looped from the registry. Parameterized by
`ENVIRONMENT`; region `eu-central-1`. A `pytest` test synthesizes the template and asserts the
expected resources and key properties exist.

### US-6 — `deploy` CLI
**DoD:** `uv run deploy` synthesizes the template, packages the Lambda artifact (handler +
embedded templates + runtime deps), runs `aws cloudformation deploy` for the chosen
`ENVIRONMENT`, and prints stack outputs (incl. `DeliveryQueueUrl`). boto3/subprocess mocked in
tests; real execution is manual.

### US-7 — `tenant-setup` CLI (semi-automated SES + Cloudflare)
**DoD:** `uv run tenant-setup <tenant>` reads the registry; per sending domain creates/looks-up
the SES domain identity, retrieves real DKIM tokens, prints **Cloudflare-ready** records (3
DKIM `CNAME` + recommended SPF/DMARC `TXT`), polls SES until verified, reports sandbox status
with production-access steps, and flags what costs money. boto3 mocked in tests; manual DNS
entry (no Cloudflare API in v1).

### US-8 — `smoke-test` CLI
**DoD:** `uv run smoke-test <tenant> <template>` enqueues a real Delivery request to the
deployed queue (default `--mode sqs`; `lambda`/`ses` as narrower diagnostics), FROM a real
Tenant identity, TO the SES mailbox simulator by default (`--to` to override; `--simulate
bounce|complaint`). `--wait` injects a correlation id and polls CloudWatch logs until success
or timeout, returning exit `0`/`1`. boto3 mocked in tests; real execution is manual.

### US-9 — Observability
**DoD:** one structured JSON log line per request with `tenant`, `template_name`, SQS message
id, SES message id, outcome, and error class. `template_data` contents are never logged; the
recipient is redacted to its domain. Tests assert log shape and redaction.

### US-10 — Repo integration
**DoD:** `notifications/pyproject.toml` declares deps (boto3, jinja2, pydantic, troposphere,
pytest, ruff); `scripts/verify.sh` runs the `notifications` project; `CLAUDE.md` gains the
`notifications/ → python skill` routing line; root `README.md` points at
`TENANT-ONBOARDING.md`.

## Implementation Decisions

- **Language/runtime:** Python 3.12 (Lambda); `uv` project, `ruff` lint+format, `pytest`.
- **IaC:** Troposphere → CloudFormation, asserted by offline synthesis. No CDK/Terraform, no
  Node toolchain. Real deploy via `aws cloudformation deploy`.
- **Templating:** Jinja2, templates embedded in the deployment artifact, one folder per Tenant.
- **Tenant config:** one typed in-repo registry, read by both infra and handler. Configuration
  set name derived (`<slug>-<environment>`), never duplicated. Sender-domain enforcement is a
  hard security invariant.
- **Reliability:** `ReportBatchItemFailures`; transient → retry via SQS; non-retriable →
  explicit DLQ forward, no retries; DLQ `maxReceiveCount = 3`; **no dedup store** (at-least-once,
  rare double-send accepted); `maximum_concurrency` set conservatively (Lambda concurrency is
  not SES msgs/sec).
- **SES:** stack creates **configuration sets only**; domain identities + sandbox exit are
  manual prerequisites, guided by `tenant-setup`.
- **Region:** `eu-central-1` default.
- **Config:** a single typed settings module (`config.py`, pydantic-settings) is the only
  reader of env vars. Runtime values are injected onto the Lambda by the stack (`ENVIRONMENT`,
  `DELIVERY_DLQ_URL`); CLIs read shell env + flags (`--env`, `--region`, `--profile`). No
  secrets in the repo; optional gitignored `.env` for local CLI use.
- **AWS auth:** the Lambda uses its IAM execution role; operator CLIs use the boto3 default
  credential chain via **AWS SSO** (`aws sso login --profile <profile>`). No static keys.
- **Tagging:** every AWS resource carries `app=notification-engine`, `environment=<env>`,
  `managed-by=email-delivery-manager` — defined once in `config.py`, applied per-resource and
  as stack-level deploy tags.
- **Operator tools** (`deploy`, `tenant-setup`, `smoke-test`) hit real AWS, run by hand,
  **outside** the Ralph/`verify.sh` loop; unit-tested with mocked boto3.

## Testing Strategy

- **Offline only in `verify.sh`.** No test touches real AWS. The SES/SQS clients are exercised
  via `botocore` Stubber / `moto`-style fakes.
- **Handler:** unit + integration tests over synthetic SQS events — rendering (incl. loops and
  a missing-template case), sender resolution + enforcement, payload validation, error
  classification, `batchItemFailures` content, and DLQ-forward behavior.
- **Infrastructure:** synthesize the Troposphere stack and assert the CloudFormation contains
  the expected resources and properties (queue/DLQ redrive, ESM settings, IAM scoping, one
  configuration set per Tenant).
- **CLIs:** unit tests with mocked boto3/subprocess; assert the right API calls, the emitted
  Cloudflare records, correlation/polling logic, and exit codes. No network.
- **Gate:** `./scripts/verify.sh` (the only verification contract) — `uv sync`, `pytest`,
  `ruff check`, `ruff format --check` for the `notifications` project, alongside the existing
  projects. Real `deploy` + `smoke-test` are manual post-deploy checks, not part of the gate.

## Out of Scope

- Dedup / idempotency store (at-least-once with rare double-send is accepted for now).
- Per-Tenant physical isolation; any self-service tenant-management UI or API.
- Runtime/DB/S3 template storage and any template-editing UI (templates are embedded + deployed).
- Multiple recipients, cc/bcc, attachments, reply-to (single recipient in v1).
- Cloudflare API automation (`--apply-dns`); DNS records are added manually in v1.
- Automated SES production-access / sandbox exit (manual, one-time).
- CI/CD for deployment (deploy is a manual operator action in v1).
- Inbound email, scheduling/delayed sends, and auto-tuning concurrency to live SES quotas.
- The dormant `api/`/`background/`/`web/`/`shared/` scaffold and any future internal site.
