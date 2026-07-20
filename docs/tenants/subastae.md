# Subastae — Tenant Onboarding Runbook

> **Status: ENGINE LIVE (2026-07-20).** Domain verified in SES (DKIM), stack deployed,
> smoke test `delivered`. Remaining: SES production access, then migrating the app
> producers off Gmail SMTP. Notes from the resume run:
>
> - The Route53 → Cloudflare migration had dropped the root SPF and `_dmarc` records;
>   both were re-added (Google SPF + `p=none` DMARC) on 2026-07-20.
> - Two pre-existing engine bugs surfaced and were fixed during the run: the send
>   policy lacked SES identity ARNs (every send got AccessDenied), and the delivery
>   logger was filtered below INFO on python3.12 (no outcome records ever logged).
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
| Templates             | `welcome`, `weekly_report`, `verify_email`, `password_reset`, `google_login_hint`, `registration_attempt`, `alert_digest`, `announcement` |

## Current state (done)

- ✅ Registered in `notifications/src/notifications/tenants.py` (alongside the demo `acme` tenant).
- ✅ Templates added under `notifications/src/notifications/templates/subastae/` (Spanish) — one per
  email the app sends today; see the producer table below for the mapping.
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
Every command below passes `--env prod` explicitly: `Settings.environment` is required (no
`notifications/.env` on a fresh checkout → hard error), and an `ENVIRONMENT` pointing elsewhere
would silently target the wrong stack.

### 1. Verify the domain in SES

```sh
uv run tenant-setup subastae --env prod --profile default
```

The tool does **one** status read per run (it is idempotent — rerunning is the intended flow),
so this is a two-pass step:

1. **First run** creates the identity, fetches the real DKIM tokens, prints the DNS records,
   and reports `dkim_status: pending` — expected, since the CNAMEs don't exist yet.
2. Add the printed records in Cloudflare (see below).
3. **Rerun** the same command to confirm verification once DNS has propagated; optionally add
   `--poll-attempts 10` to keep polling within a single run.

**In Cloudflare, from what it prints:**

- ✅ Add the **3 DKIM `CNAME`** records (`<token>._domainkey.subastae.com → <token>.dkim.amazonses.com`). Unique
  selectors — safe, additive, no clash with Google's `google._domainkey`.
- ❌ **Do NOT add the suggested SPF `TXT`.** You already have a Google SPF, and only one SPF record is allowed; a second
  breaks email auth. DKIM alignment alone satisfies DMARC for SES. If you later adopt a custom MAIL FROM, do **not**
  touch the root SPF: the CLI's MAIL FROM domain is `mail.subastae.com`, SES evaluates SPF against that envelope
  subdomain, so publish the printed **MX and SPF `TXT` records at `mail.subastae.com`** instead.
- ❌ **Don't duplicate DMARC** — keep the existing record.
- ✋ **Leave MX alone** — SES sending doesn't change receiving.

### 2. Redeploy

The registry changed, so the stack must create `subastae-prod` and bundle the new templates:

```sh
uv run deploy --env prod --profile default --artifact-bucket global-notification-engine-artifacts
```

### 3. Smoke-test

`welcome` requires a `name` (strict templating), so pass `--data` or it errors before SES.
Use `--wait` — without it the CLI exits as soon as SQS accepts the message, before the Lambda
has even run. With it, the CLI injects a correlation id, polls CloudWatch Logs for *this*
message's delivery record, and exits nonzero on rejection or timeout:

```sh
uv run smoke-test subastae welcome --env prod --profile default --data '{"name":"Prueba"}' --wait
```

**Success:** exit code 0 and the correlated log line with `outcome:"delivered"` and a real SES
message id (the mailbox simulator accepts it). For ad-hoc debugging only:
`aws logs tail /aws/lambda/notification-engine-delivery-prod --region eu-central-1 --profile default --since 5m --format short`.

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

## App migration — producers to move off Gmail SMTP

The goal of this onboarding: `hola@subastae.com` mail currently goes out via `smtplib` +
Google SMTP directly from the app (`SMTP_HOST/PORT/USER/PASS/FROM` env vars in
`auctions_scraper`). Once the domain is verified and SES production access is granted, these
call sites migrate to enqueueing the JSON payload above instead of speaking SMTP:

| Producer (in `auctions_scraper/src/`)          | Sends                                        | Engine template(s)                                                        |
|------------------------------------------------|----------------------------------------------|---------------------------------------------------------------------------|
| `routers/auth_router.py`                       | email verification                           | `verify_email` (`verify_url`)                                              |
| `routers/auth_router.py`                       | password reset                               | `password_reset` (`reset_url`, `expiry_minutes`)                           |
| `routers/auth_router.py`                       | "your account uses Google" hint              | `google_login_hint` (`login_url`)                                          |
| `routers/auth_router.py`                       | registration-attempt notice                  | `registration_attempt` (`login_url`)                                       |
| `auctions/management/weekly_email_delivery.py` | weekly Excel report (download link)          | `weekly_report` (`hero_title`, `hero_copy`, `download_url`, `available_until_date`, `account_url`) |
| `auctions/management/dispatch_alerts.py`       | alert digest (new lot, price drop, ending soon, favorites) | `alert_digest` (`hero_title`, `hero_subtitle`, `sections[]`, `unsubscribe_url`) |
| `auctions/management/announcements.py`         | one-off announcements                        | `announcement` (`title`, `paragraphs[]`, `cta_label`, `cta_url`)            |

All templates exist under `templates/subastae/` with strict, tested variable contracts —
`tests/unit/test_rendering.py` documents the exact `template_data` each producer must enqueue.
Rendering is `StrictUndefined`: every listed variable is required (pass `""`/`0` to disable an
optional block — the announcement CTA, a card's discount, or the digest's unsubscribe link for
favorites-only digests, which carry no alert-unsubscribe URL). Subjects stay producer-side —
they travel as the payload's `subject` field, not in the template. `weekly_report` renders the
real Excel-download email (not the earlier metrics placeholder). The SES path also removes the
SMTP throttle/retry workarounds those modules carry (burst-load disconnects on ~1/sec sends,
the 2026-07-06 `SMTPServerDisconnected` incident).

## Onboarding checklist

- [x] Tenant registered in `tenants.py`
- [x] Templates added under `templates/subastae/`
- [x] Gate green / committed
- [x] DNS migrated Route53 → Cloudflare (Google email records carried over; missing SPF/DMARC re-added 2026-07-20)
- [x] `tenant-setup subastae --env prod` (run 1) → 3 DKIM CNAMEs added in Cloudflare → rerun → verified (2026-07-20)
- [ ] SES production access (out of sandbox) for real recipients
- [x] `uv run deploy --env prod` (creates `subastae-prod`) (2026-07-20)
- [x] `smoke-test subastae welcome --env prod --data '{"name":"…"}' --wait` → exit 0, `delivered` (2026-07-20)
- [ ] App producers migrated off Gmail SMTP (see "App migration" above)
