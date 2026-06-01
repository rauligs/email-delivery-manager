---
status: accepted
---

# Serverless SES notification engine inside the Ralph monorepo

We are building a multi-tenant email **Notification Engine** (see [CONTEXT.md](../../CONTEXT.md))
as a serverless AWS pipeline — SQS → Lambda → SES — added as one new Python module
(`notifications/`) to this otherwise FastAPI/Postgres/Docker monorepo. The existing
`api/`/`background/`/`web/`/`shared/` scaffold stays dormant for now. We chose this shape
because the repo is driven by `ralph.sh`, an AFK agent loop whose only verification is an
**offline** `scripts/verify.sh` (pytest + ruff, no AWS credentials), so the entire system —
handler *and* infrastructure — must be authored and verified without touching real AWS. The
default region is `eu-central-1` (Frankfurt).

## Considered options

- **Infrastructure as code: Troposphere (chosen)** over AWS CDK (Python) and Terraform/OpenTofu.
  Troposphere is pure-Python, installed by `uv` like every other dependency, and synthesizes
  CloudFormation that a `pytest` test asserts on — 100% offline, no Node/`cdk` CLI, no provider
  downloads. CDK and Terraform both drag a second toolchain and network steps into a
  uv/pytest verification contract for no benefit at this scale. Real deploys use
  `aws cloudformation deploy` on the synthesized template, by hand, outside the Ralph loop.
- **Home of the system: in this monorepo (chosen)** over a separate standalone repo. The repo
  already provides the Ralph workflow, skill routing, and verification contract we want to
  build under; a separate repo would duplicate all of it.
- **Tenant isolation: logical, not physical.** All Tenants are the operator's own private
  projects, not external customers, so embedded templates and shared IAM are acceptable; we
  explicitly did *not* build per-Tenant physical isolation, a dedup/idempotency store, or any
  self-service surface.

## Consequences

- Nothing in `verify.sh` may call real AWS. The handler is tested against a **stubbed SES
  client**; the infrastructure is verified by **offline CloudFormation synthesis**. Live
  `deploy` and live sends are manual, out-of-loop operator actions.
- SES domain identities and SES production access are **manual prerequisites**, not managed by
  the stack (the stack creates configuration sets only). A guided `tenant-setup` CLI walks the
  operator through SES identity + DKIM (Cloudflare DNS) + sandbox exit.
- Delivery is **at-least-once with no dedup store**: a crash between an SES accept and the SQS
  delete can rarely double-send. Accepted deliberately; revisit if a Tenant ever sends
  one-time-code or invoice email.
- `verify.sh` gains a `notifications` project entry and `CLAUDE.md` gains a
  `notifications/ → python skill` routing line.
- Config is read by one settings module; runtime env vars are injected onto the Lambda by the
  stack, operator CLIs authenticate via AWS SSO (no static keys), and every resource is tagged
  `app` / `environment` / `managed-by` for provenance.
