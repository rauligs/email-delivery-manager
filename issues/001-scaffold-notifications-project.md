# Scaffold the `notifications/` Python project and wire it into the repo

**Priority tier:** Infrastructure

Foundation for the serverless notification engine (PRD US-10, ADR 0001). Python/`uv`
module, routed to the `python` skill. No AWS calls in this issue.

## Acceptance criteria

- `notifications/` exists with:
  - `pyproject.toml` declaring runtime deps `boto3`, `jinja2`, `pydantic` (v2), `troposphere`
    and dev deps `pytest`, `ruff`; a console-scripts table is fine to stub for later CLIs.
  - `src/notifications/__init__.py` package layout and `tests/unit/` + `tests/integration/`.
  - Ruff configured to match repo conventions.
- `uv run pytest`, `uv run ruff check .`, and `uv run ruff format --check .` all pass for the
  module (a trivial placeholder test is acceptable here).
- `scripts/verify.sh` runs the new module (e.g. `run_python_project notifications`) and the
  full `./scripts/verify.sh` passes end to end.
- `CLAUDE.md` and `GEMINI.md` "Required Skill Routing" sections gain a line routing
  `notifications/` → the `python` skill (`.claude/skills/python/SKILL.md` and
  `.gemini/skills/python/SKILL.md` respectively).
- Root `README.md` Structure section lists `notifications/` and points to
  `TENANT-ONBOARDING.md`.
- A typed settings module `src/notifications/config.py` (pydantic-settings) is the single
  reader of environment variables, with documented defaults: `ENVIRONMENT` (required at
  runtime), `AWS_REGION` (default `eu-central-1`), `AWS_PROFILE` (optional, for SSO), and
  `DELIVERY_DLQ_URL` (injected by the stack at runtime). Optional `.env` support for local CLI
  use only (non-secret values; `.env` is gitignored).
- A shared "standard tags" helper returns the tag set applied to every AWS resource:
  `app=notification-engine`, `environment=<env>`, `managed-by=email-delivery-manager`.

## Dependencies

- None.
