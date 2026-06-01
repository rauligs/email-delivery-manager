# Walking skeleton — render a template and send via SES (mocked), with a minimal stack

**Priority tier:** Tracer Bullet

PRD US-1. The thinnest end-to-end path crossing handler + infrastructure + tests, so the
whole pipeline is exercised before any feature is fleshed out.

## Acceptance criteria

- A Lambda handler entrypoint accepts an SQS event and processes each record.
- For a record it loads `src/notifications/templates/<tenant>/<template_name>.html` from the
  embedded filesystem and renders it with Jinja2 using `template_data`, including a
  `{% for %}` table/list loop.
- It builds an SES `SendEmail` request (From, To, Subject, HTML body) and calls SES through a
  small adapter; the adapter is **stubbed/faked in tests** (botocore `Stubber` or `moto`) —
  no real AWS, no network.
- Sample fixtures exist for one tenant: `welcome.html` and `weekly_report.html` (the latter
  with a table loop driven by `template_data`).
- A minimal Troposphere stack at `src/notifications/infra/stack.py` synthesizes a delivery
  SQS queue, the Lambda function, and an IAM execution role; an **offline** test asserts those
  resources appear in the synthesized CloudFormation (synthesis only, never a deploy).
- Every resource the stack creates carries the standard tag set (`app`, `environment`,
  `managed-by`) from `config.py`, and the Lambda's `Environment.Variables` include
  `ENVIRONMENT`; the offline synth test asserts both.
- Unit tests assert the rendered HTML (including loop output) and the SES call arguments.
- `./scripts/verify.sh` passes.

## Dependencies

- 001
