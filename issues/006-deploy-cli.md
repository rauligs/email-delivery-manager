# `deploy` operator CLI — package and CloudFormation deploy

**Priority tier:** Tracer Bullet

PRD US-6. An out-of-loop operator tool: it touches real AWS only when a human runs it; in the
Ralph/`verify.sh` loop its boto3/subprocess calls are mocked.

## Acceptance criteria

- A console script (`uv run deploy`) that:
  - resolves config via `config.py` and flags `--env`/`ENVIRONMENT`, `--region` (default
    `eu-central-1`), and `--profile`/`AWS_PROFILE`; AWS auth uses the boto3 default chain, so
    `aws sso login --profile <profile>` is the only operator prerequisite (no static keys);
  - synthesizes the Troposphere template;
  - packages the Lambda artifact (handler + embedded templates + runtime deps);
  - invokes `aws cloudformation deploy` for the target `ENVIRONMENT` (default region
    `eu-central-1`), passing the standard tag set as stack-level `--tags`;
  - prints the stack outputs, including the delivery queue URL (`DeliveryQueueUrl`).
- `argparse`-based CLI; returns a non-zero exit on failure; no tracebacks shown to operators.
- Unit tests with **mocked** boto3/subprocess assert that the template is synthesized and that
  the deploy command and parameters are correct. No real AWS, no network.
- `./scripts/verify.sh` passes.

## Dependencies

- 001, 005
