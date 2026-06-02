# Subastae — Tenant Onboarding Runbook

> **Status: PARKED (2026-06-02).** Waiting on the `subastae.com` DNS migration from
> **Route53 → Cloudflare**. Resume the steps below once Cloudflare is authoritative.
>
> Per-tenant companion to the general guides:
> [TENANT-ONBOARDING.md](../../TENANT-ONBOARDING.md) and [DEPLOYMENT.md](../../DEPLOYMENT.md).

## Tenant at a glance

| Field                 | Value                                          |
|-----------------------|------------------------------------------------|
| Slug                  | `subastae`                                     |
| Sending domain        | `subastae.com`                                 |
| Default sender        | `hola@subastae.com`                            |
| Environment           | `prod` (region `eu-central-1`)                 |
| SES configuration set | `subastae-prod` (derived, never written twice) |
| Templates             | `welcome`, `weekly_report`                     |

## Current state (done)

- ✅ Registered in `notifications/src/notifications/tenants.py` (alongside the demo `acme` tenant).
- ✅ Templates added: `notifications/src/notifications/templates/subastae/{welcome,weekly_report}.html` (Spanish).
- ✅ Committed on `main`; full verification gate green.
- ✅ Engine infrastructure already deployed and healthy (queue, DLQ, Lambda — packaging + timeout fixes live).

## Blocker

`subastae.com` is a **live domain currently sending via Google (Workspace/Gmail SMTP)** to real
users, and its DNS is mid-migration from **Route53 → Cloudflare**. SES DKIM verification must
wait until Cloudflare is the authoritative zone — otherwise the DKIM records land on the
retiring Route53 zone and have to be re-verified after cutover.

### During the Route53 → Cloudflare migration

Carry these existing records over to Cloudflare, or live app email breaks:

- **MX** → Google (receiving).
- **SPF** `TXT` → `v=spf1 include:_spf.google.com …` (exactly one SPF record allowed).
- **DKIM** → `google._domainkey` (Google's selector).
- **DMARC** → existing `_dmarc` `TXT`.

Add the SES DKIM records **only after** Cloudflare is authoritative.

## Resume checklist (run once DNS is on Cloudflare)

All commands run from `notifications/`. Ensure an SSO session first: `aws sso login --profile default`.

### 1. Verify the domain in SES

```sh
uv run tenant-setup subastae --profile default
```

It fetches real DKIM tokens, prints DNS records, and polls until SES sees them verified. Have
Cloudflare open to add records while it polls.

**In Cloudflare, from what it prints:**

- ✅ Add the **3 DKIM `CNAME`** records (`<token>._domainkey.subastae.com → <token>.dkim.amazonses.com`). Unique
  selectors — safe, additive, no clash with Google's `google._domainkey`.
- ❌ **Do NOT add the suggested SPF `TXT`.** You already have a Google SPF, and only one SPF record is allowed; a second
  breaks email auth. DKIM alignment alone satisfies DMARC for SES. Only ever *merge* `include:amazonses.com` into the
  existing SPF if you later adopt a custom MAIL FROM.
- ❌ **Don't duplicate DMARC** — keep the existing record.
- ✋ **Leave MX alone** — SES sending doesn't change receiving.

### 2. Redeploy

The registry changed, so the stack must create `subastae-prod` and bundle the new templates:

```sh
uv run deploy --env prod --profile default --artifact-bucket global-notification-engine-artifacts
```

### 3. Smoke-test

`welcome` requires a `name` (strict templating), so pass `--data` or it errors before SES:

```sh
uv run smoke-test subastae welcome --profile default --data '{"name":"Prueba"}'
aws logs tail /aws/lambda/notification-engine-delivery-prod --region eu-central-1 --profile default --since 5m --format short
```

**Success:** a structured log line with `outcome:"delivered"` and a real SES message id (the
mailbox simulator accepts it).

## Notes

- **SES sandbox:** the account is likely still in the SES sandbox — sending works only to
  verified addresses and the mailbox simulator. `tenant-setup` reports sandbox status and the
  steps to request production access. Real `subastae` users can only receive via SES after
  production access is granted.
- **No disruption while parked:** the registered tenant is inert until its domain is verified;
  SES sending runs in parallel to the live Gmail path. The app keeps using Google SMTP until
  its producers are migrated to enqueue onto the delivery queue.
- **Payload to enqueue** (for the eventual app migration):
  ```json
  {"tenant": "subastae", "template_name": "welcome", "to": "user@example.com", "subject": "…", "template_data": {"name": "…"}}
  ```

## Onboarding checklist

- [x] Tenant registered in `tenants.py`
- [x] Templates added under `templates/subastae/`
- [x] Gate green / committed
- [ ] DNS migrated Route53 → Cloudflare (Google email records carried over)
- [ ] `tenant-setup subastae` → 3 DKIM CNAMEs added in Cloudflare → verified
- [ ] SES production access (out of sandbox) for real recipients
- [ ] `uv run deploy` (creates `subastae-prod`)
- [ ] `smoke-test subastae welcome --data '{"name":"…"}'` → `delivered`
