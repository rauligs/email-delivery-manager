# Tenant Onboarding & Integration Guide

How to onboard one of your projects as a **Tenant** of the Notification Engine and send
email through it.

> **Status:** this documents the *agreed design* (see [CONTEXT.md](./CONTEXT.md) and
> [docs/adr/0001-serverless-ses-notification-engine.md](./docs/adr/0001-serverless-ses-notification-engine.md)).
> The `notifications/` module and its CLIs are built via the PRD/issues — paths and command
> names here are the contract those issues implement, not yet-existing files.

## Concepts (quick)

| Term | Meaning |
|------|---------|
| **Tenant** | One of your sending products. Owns its templates, an SES configuration set, a default sender, and its permitted sending domains. Identified by a stable slug (`acme`). |
| **Environment** | A whole deployment of the engine (`prod`, `staging`). The same Tenants exist in each. Not part of a Tenant's id. |
| **Delivery request** | The JSON message you enqueue to ask for one email to be rendered and sent. |
| **Template** | A named Jinja2 HTML file owned by a Tenant. |
| **Sender identity** | The `from_address` an email is sent as — must belong to the Tenant's permitted domains. |

Full glossary: [CONTEXT.md](./CONTEXT.md).

---

## Part 1 — Onboard a new Tenant (do this once per project)

Follow these steps in order. All commands run from the repo root.

> **Operator prerequisites.** The CLIs (`deploy`, `tenant-setup`, `smoke-test`) authenticate
> via the standard boto3 credential chain, so log in first with
> **`aws sso login --profile <your-profile>`** and pass `--profile`/`AWS_PROFILE` (no static
> keys). Default region is `eu-central-1`; select the deployment with `--env <prod|staging>`.
> Every AWS resource created is tagged `app=notification-engine`, `environment=<env>`,
> `managed-by=email-delivery-manager` for provenance and cost tracking.

### 1. Register the Tenant

Add an entry to the registry at `notifications/src/notifications/tenants.py` — the single
source of truth read by *both* the infrastructure and the runtime handler:

```python
TENANTS = {
    # slug          default sender                 domains it may send from
    "acme": Tenant(slug="acme", default_from="hello@acme.com", from_domains={"acme.com"}),
}
```

- `slug` is what you put in the `tenant` field of every Delivery request.
- `from_domains` is enforced: a request whose `from_address` is outside these domains is
  **rejected** (no cross-Tenant spoofing).
- The SES configuration set name is **derived**, not stored: `<slug>-<environment>`
  (e.g. `acme-prod`). You never write it down twice.

### 2. Add templates

Create one Jinja2 HTML file per email type under the Tenant's folder:

```
notifications/src/notifications/templates/acme/welcome.html
notifications/src/notifications/templates/acme/weekly_report.html
```

The filename (without `.html`) is the `template_name` you send. See the
[template example](#template-example) below for loops/tables.

### 3. Verify the sending domain in SES (Cloudflare DNS)

```sh
uv run tenant-setup acme
```

This creates/looks up the SES domain identity for each of the Tenant's `from_domains`,
prints the **exact records to add in Cloudflare** (3 DKIM `CNAME`s, plus recommended SPF and
DMARC `TXT`), then polls SES until the domain is verified. Add the records in the Cloudflare
dashboard for the zone, then let it finish.

It also reports whether the AWS account is still in the **SES sandbox**. If it is, request
production access once via the SES console (the script prints the steps); until then you can
only send to verified recipients and the mailbox simulator.

> SES domain identities and configuration sets are free; **sending** is billed per email.

### 4. Deploy the Environment

```sh
uv run deploy            # aws cloudformation deploy of the synthesized template
```

This creates the Tenant's configuration set in the target Environment (and packages the
Lambda with the new templates). Set the target with `ENVIRONMENT=prod` (default region is
`eu-central-1`, Frankfurt).

### 5. Smoke-test the deployed pipeline

```sh
uv run smoke-test acme welcome --wait
```

Sends a real Delivery request end-to-end through the live SQS queue, FROM your verified
domain, TO the SES mailbox simulator (safe — no real inbox, no reputation hit), then polls
CloudWatch logs until it confirms success. Exit code `0` = the deploy works.

To eyeball a real message: `uv run smoke-test acme welcome --to you@acme.com`.
To exercise bounce/complaint handling + config-set metrics: `--simulate bounce|complaint`.

### Onboarding checklist

- [ ] Tenant entry added to `tenants.py` (slug, default_from, from_domains)
- [ ] Template(s) added under `templates/<slug>/`
- [ ] `uv run tenant-setup <slug>` → DKIM/SPF/DMARC added in Cloudflare → verified
- [ ] SES production access confirmed (out of sandbox) for real recipients
- [ ] `uv run deploy` (correct `ENVIRONMENT`)
- [ ] `uv run smoke-test <slug> <template> --wait` exits `0`

---

## Part 2 — Integrate: send a Delivery request

Your project sends email by enqueuing a JSON **Delivery request** onto the engine's SQS
queue. You do **not** call SES yourself.

### The queue

The queue URL is a CloudFormation **stack output** of the deployed Environment
(`DeliveryQueueUrl`). Read it once and configure it in your project.

### Payload schema

```json
{
  "tenant": "acme",                     // required — your Tenant slug
  "template_name": "welcome",           // required — a template file under templates/acme/
  "to": "user@example.com",             // required — single recipient
  "subject": "Welcome to Acme",         // required
  "from_name": "Acme",                  // optional — display name
  "from_address": "hello@acme.com",     // optional — must be within the Tenant's from_domains;
                                        //            omitted → the Tenant's default_from is used
  "template_data": {                    // optional — values passed to the Jinja2 template
    "first_name": "Sam",
    "items": [
      { "name": "Report A", "value": 42 },
      { "name": "Report B", "value": 17 }
    ]
  }
}
```

Rules:
- Unknown `tenant`, missing `template_name` file, schema-invalid payload, or a `from_address`
  outside the Tenant's domains are **non-retriable** — logged and routed to the DLQ, not retried.
- Transient SES errors (throttling/5xx) are retried automatically.

### Enqueue (Python / boto3)

```python
import json, boto3

sqs = boto3.client("sqs", region_name="eu-central-1")
sqs.send_message(
    QueueUrl=DELIVERY_QUEUE_URL,
    MessageBody=json.dumps({
        "tenant": "acme",
        "template_name": "welcome",
        "to": "user@example.com",
        "subject": "Welcome to Acme",
        "template_data": {"first_name": "Sam"},
    }),
)
```

### Enqueue (AWS CLI)

```sh
aws sqs send-message --region eu-central-1 \
  --queue-url "$DELIVERY_QUEUE_URL" \
  --message-body '{"tenant":"acme","template_name":"welcome","to":"user@example.com","subject":"Welcome to Acme"}'
```

---

## Part 3 — Observe & verify

- **CloudWatch Logs** (Lambda log group): one structured line per request with `tenant`,
  `template_name`, the SQS message id, the SES message id, outcome, and error class. Template
  data is never logged; the recipient is redacted to its domain.
- **Per-Tenant metrics**: bounces/complaints/deliveries are separated by each Tenant's SES
  configuration set (`<slug>-<environment>`).
- **DLQ**: messages that failed `maxReceiveCount = 3` times land in the dead-letter queue for
  inspection.

> Delivery is at-least-once with **no dedup store** — a rare crash between an SES accept and
> the SQS delete can double-send. Acceptable for current (non-critical) projects; revisit
> before sending one-time codes or invoices.

---

## Template example

`notifications/src/notifications/templates/acme/weekly_report.html` — a Jinja2 table loop
driven by `template_data.items`:

```html
<h1>Weekly report for {{ first_name }}</h1>
<table>
  <thead><tr><th>Name</th><th>Value</th></tr></thead>
  <tbody>
    {% for item in items %}
    <tr><td>{{ item.name }}</td><td>{{ item.value }}</td></tr>
    {% endfor %}
  </tbody>
</table>
{% if not items %}<p>No activity this week.</p>{% endif %}
```
