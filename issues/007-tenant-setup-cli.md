# `tenant-setup` operator CLI — SES identity + DKIM (Cloudflare) + sandbox guidance

**Priority tier:** Polishing

PRD US-7. Out-of-loop operator tool; real AWS only when run by hand, boto3 mocked in tests.
Turns the "verify the domain first" prerequisite into a guided, semi-automated step.

## Acceptance criteria

- A console script (`uv run tenant-setup <tenant>`) that:
  - resolves config/auth via `config.py` and `--profile`/`AWS_PROFILE` (boto3 default chain;
    `aws sso login` is the operator prerequisite, no static keys);
  - reads the registry and, for each of the Tenant's `from_domains`, creates/looks-up the SES
    domain identity (tagged with the standard tag set) and retrieves its DKIM tokens;
  - prints **Cloudflare-ready** DNS records: 3 DKIM `CNAME`s plus recommended SPF and DMARC
    `TXT` records (and a MAIL FROM suggestion);
  - polls SES verification status and reports progress;
  - reports whether the account is in the SES sandbox, with the production-access request
    steps, and flags what incurs cost.
- `argparse`-based CLI; non-zero exit on failure; idempotent (re-running for an already
  verified domain is safe and just reports current status).
- Manual DNS entry only — no Cloudflare API in v1.
- Unit tests **mock** boto3 and assert the emitted records and status handling. No real AWS,
  no network.
- `./scripts/verify.sh` passes.

## Dependencies

- 004
