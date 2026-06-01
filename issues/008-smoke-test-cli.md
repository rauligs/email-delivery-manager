# `smoke-test` operator CLI — live end-to-end send + deploy verification

**Priority tier:** Polishing

PRD US-8. Out-of-loop operator tool; real AWS only when run by hand, boto3/logs mocked in
tests. Proves a *deployed* Environment actually works.

## Acceptance criteria

- A console script (`uv run smoke-test <tenant> <template>`) that:
  - enqueues a real Delivery request to the deployed queue by default (`--mode sqs`), with
    `--mode lambda|ses` as narrower diagnostics;
  - sends FROM a real Tenant identity, TO `success@simulator.amazonses.com` by default; `--to`
    overrides to a real address, and `--simulate bounce|complaint` targets the matching SES
    mailbox-simulator addresses;
  - reads the deployed queue URL from the CloudFormation stack outputs for the target
    `ENVIRONMENT`.
- `--wait` injects a unique correlation id and polls CloudWatch Logs until it observes the
  correlated success (and SES message id) or times out; exit `0` on success, `1` on
  failure/timeout.
- `argparse`-based CLI; non-zero exit on failure.
- Unit tests **mock** boto3 + logs and assert message construction, simulator/override
  addresses, correlation/polling logic, and exit codes. No real AWS, no network.
- `./scripts/verify.sh` passes.

## Dependencies

- 006, 004
