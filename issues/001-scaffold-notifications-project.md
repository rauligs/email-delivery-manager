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

## Dependencies

- None.
