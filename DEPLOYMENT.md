# Infrastructure Deployment Guide

How to stand up (and redeploy) the **Notification Engine** infrastructure for an
Environment with the operator `deploy` CLI.

> **Companion docs:** [TENANT-ONBOARDING.md](./TENANT-ONBOARDING.md) covers per-Tenant
> setup (domains, DKIM, templates). This guide covers the shared
> **SQS → Lambda → SES** stack itself. Design record: [CONTEXT.md](./CONTEXT.md),
> [docs/adr/0001](./docs/adr/0001-serverless-ses-notification-engine.md).

## What gets deployed

`uv run deploy` synthesizes a Troposphere → CloudFormation template and deploys it as a
single stack named **`notification-engine-<environment>`**. One stack per Environment
(`prod`, `staging`); the same Tenants exist in each.

| Resource                             | Notes                                                                                                                                                              |
|--------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Delivery queue** (SQS)             | What producers enqueue against. URL surfaced as stack output `DeliveryQueueUrl`.                                                                                   |
| **Dead-letter queue** (SQS)          | Redrive target; messages land here after `maxReceiveCount = 3`.                                                                                                    |
| **Lambda** (`python3.12`)            | Handler `notifications.handler.handler`; code pulled from S3. `ENVIRONMENT` + `DELIVERY_DLQ_URL` injected as env vars.                                             |
| **Event-source mapping**             | SQS → Lambda: batch size 10, 5s batching window, `ReportBatchItemFailures`, `MaximumConcurrency = 2`.                                                              |
| **IAM execution role**               | Least-privilege: `ses:SendEmail` scoped to the Tenants' configuration sets, SQS receive/delete on the source queue, `sqs:SendMessage` on the DLQ, CloudWatch Logs. |
| **SES configuration set** per Tenant | One per entry in the registry, named `<slug>-<environment>` (e.g. `acme-prod`). Gives per-Tenant bounce/complaint metrics.                                         |

Every taggable resource carries `app=notification-engine`, `environment=<env>`,
`managed-by=email-delivery-manager`.

> **Not created by the stack:** SES **domain identities** and **sandbox exit** are manual,
> per-Tenant prerequisites — see [TENANT-ONBOARDING.md](./TENANT-ONBOARDING.md) step 3
> (`tenant-setup`). The stack creates *configuration sets only*. The **S3 artifact bucket**
> is a one-time prerequisite you create yourself (below).

## Prerequisites

- **AWS CLI v2** on the operator's `PATH` (the CLI shells out to `aws s3 cp` and
  `aws cloudformation deploy`).
- **An active AWS SSO session.** All AWS access uses the boto3 default credential chain — no
  static keys. Log in first:
  ```sh
  aws sso login --profile <your-profile>
  ```
  Your role needs permission to create the stack's resources (CloudFormation, Lambda, SQS,
  IAM role, SES configuration sets) and to write to the artifact bucket.
- **`uv`** and the `notifications` project synced (`cd notifications && uv sync`).
- **At least one Tenant registered** in `notifications/src/notifications/tenants.py` — the
  stack loops one SES configuration set per Tenant from that registry.

### One-time: create the S3 artifact bucket

The `deploy` CLI **uploads** the packaged Lambda zip to S3 but does **not** create the
bucket. Create one per account (reused across environments), e.g.:

```sh
aws s3api create-bucket \
  --bucket global-notification-engine-artifacts \
  --region eu-central-1 \
  --create-bucket-configuration LocationConstraint=eu-central-1 \
  --profile <your-profile>

# Recommended: block public access + enable versioning
aws s3api put-public-access-block --bucket global-notification-engine-artifacts \
  --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true \
  --profile <your-profile>
aws s3api put-bucket-versioning --bucket global-notification-engine-artifacts \
  --versioning-configuration Status=Enabled --profile <your-profile>
```

## Configuration

The `deploy` CLI reads config through the typed settings module; **CLI flags override
environment variables**.

| Flag                      | Env var                  | Default        | Meaning                                     |
|---------------------------|--------------------------|----------------|---------------------------------------------|
| `--env` / `--environment` | `ENVIRONMENT`            | *(required)*   | Deployment target, e.g. `staging`, `prod`.  |
| `--region`                | `AWS_REGION`             | `eu-central-1` | Region to deploy to.                        |
| `--profile`               | `AWS_PROFILE`            | *(none)*       | Named profile for the local SSO session.    |
| `--artifact-bucket`       | `DEPLOY_ARTIFACT_BUCKET` | *(required)*   | S3 bucket for the packaged Lambda artifact. |

For local convenience you may keep non-secret operator config in a gitignored
`notifications/.env` (e.g. `AWS_PROFILE`, `DEPLOY_ARTIFACT_BUCKET`). Never commit secrets;
runtime secrets are injected by the stack, not the repo.

## Deploy

From `notifications/`:

```sh
uv run deploy \
  --env prod \
  --region eu-central-1 \
  --artifact-bucket global-notification-engine-artifacts
```

The CLI runs this pipeline, surfacing friendly one-line errors (never a traceback) and a
non-zero exit on any failure:

1. **Synthesize** the Troposphere template for the target Environment.
2. **Package** the Lambda zip — handler + embedded `templates/` + runtime deps (Jinja2;
   `boto3`/`botocore` ship with the runtime). Jinja2 is pure-Python, so packaging is
   portable from macOS/Linux operators alike.
3. **Upload** the zip to `s3://<bucket>/notification-engine/<env>/<sha256>.zip`. The key is
   **content-addressed**: an unchanged build reuses the same object (redeploy is a no-op);
   any code/template change yields a new key, so CloudFormation updates the function.
4. **`aws cloudformation deploy`** with `CAPABILITY_IAM`, `--no-fail-on-empty-changeset`,
   the standard tag set, and the artifact's S3 location as parameter overrides.
5. **Print stack outputs**, leading with `DeliveryQueueUrl`.

On success it prints, e.g.:

```
Deployed notification-engine-prod. Stack outputs:
  DeliveryQueueUrl = https://sqs.eu-central-1.amazonaws.com/<acct>/notification-engine-prod-...
```

Hand that `DeliveryQueueUrl` to producers — it's what they enqueue Delivery requests against
(see [TENANT-ONBOARDING.md → Part 2](./TENANT-ONBOARDING.md#part-2--integrate-send-a-delivery-request)).

## Redeploy

Run the **same command** again. You must redeploy whenever you change:

- **Handler code** under `notifications/src/notifications/` (new content-addressed key →
  function updated).
- **Templates** under `templates/<slug>/` (they are bundled into the artifact at package
  time — not stored in S3/DB).
- **The Tenant registry** `tenants.py` (adds/removes the per-Tenant SES configuration set).

A redeploy with no changes is a safe no-op (`--no-fail-on-empty-changeset`).

## Verify the deployment

```sh
uv run smoke-test <tenant> <template> --wait
```

Sends a real Delivery request end-to-end through the live queue, FROM a verified Tenant
identity, TO the SES mailbox simulator by default (no real inbox, no reputation hit), then
polls CloudWatch Logs until success. Exit `0` = the pipeline works. See
[TENANT-ONBOARDING.md](./TENANT-ONBOARDING.md) step 5 for `--to` / `--simulate` options.

## Deployment checklist

- [ ] AWS SSO session active (`aws sso login --profile <profile>`)
- [ ] S3 artifact bucket exists (one-time)
- [ ] Target Tenant(s) registered in `tenants.py`
- [ ] `uv run deploy --env <env> --artifact-bucket <bucket>` succeeds
- [ ] `DeliveryQueueUrl` captured and handed to producers
- [ ] `uv run smoke-test <tenant> <template> --wait` exits `0`

## Notes & limits

- **Region:** defaults to `eu-central-1` (Frankfurt); override with `--region`.
- **At-least-once delivery, no dedup store** — a rare crash between SES accept and SQS delete
  can double-send. Acceptable for current projects; revisit before one-time codes/invoices.
- **Concurrency:** `MaximumConcurrency = 2` is a conservative Lambda cap, **not** an SES
  messages/second rate — tune in `infra/stack.py` if needed.
- **Offline-tested, manually deployed:** the stack is asserted by offline synthesis in
  `pytest`; real `deploy`/`smoke-test` are manual operator actions outside the
  `scripts/verify.sh` gate. There is no CI/CD for deployment in v1.
- **Teardown:** delete the CloudFormation stack
  (`aws cloudformation delete-stack --stack-name notification-engine-<env> --region <region>
  --profile <profile>`). SES domain identities and the artifact bucket are not part of the
  stack and are removed separately if desired.
