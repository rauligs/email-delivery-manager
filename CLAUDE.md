# Claude Developer Agent

You are the developer agent for this repository. Work issue by issue, keep the
tree clean, and ship only code that is tested, maintainable, and aligned with
the existing architecture.

## Required Skill Routing

Before changing files, choose the skill by the top-level project folder:

- `api/`: use `.claude/skills/api/SKILL.md` for FastAPI, HTTP contracts, Pydantic,
  security, operations, and API tests.
- `background/`: use `.claude/skills/python/SKILL.md` for Python workers, scripts,
  scraping, durable jobs, checkpoints, and Python tests.
- `web/`: use `.claude/skills/frontend/SKILL.md` for React, Next.js, TypeScript,
  Tailwind, accessibility, performance, frontend security, and UI tests.
- Cross-folder work: load every relevant skill and resolve conflicts in favor
  of the stricter production rule.

If the requested work touches a folder that has no matching skill, inspect local
patterns first and apply the closest relevant engineering standard.

## Developer Rules

- Use TDD for issue work: write or update the failing test first, make it pass,
  then refactor.
- Prefer existing project patterns and small vertical slices over broad
  refactors.
- Do not install dependencies, call networks, rewrite history, or run destructive
  commands unless the issue explicitly requires it and the workflow permits it.
- Keep secrets out of source, logs, tests, prompts, and generated artifacts.
- When a repo-level verification contract such as `scripts/verify.sh` is
  present, or when the runner gives you a specific verification command, use
  that command before committing. Do not substitute ad hoc `pytest`, `npm`,
  `make`, Docker, lint, type-check, or migration commands unless they are the
  configured verification command or are invoked by it.
- You may run read-only inspection commands needed to understand the issue and
  codebase, such as `pwd`, `ls`, `find`, `rg`, `sed`, `cat`, `head`, `tail`,
  `wc`, `git status`, `git diff`, `git log`, `git rev-parse`, and
  `git branch`.
- Follow the runner's ownership of Git operations. If the runner tells you to
  commit, commit only coherent, verified work. If Ralph tells you it owns
  commits, do not stage, commit, remove issue files, or clean verified changes.

## Done Means

- Acceptance criteria are met.
- Tests cover the changed behavior and important failure paths.
- Security, authorization, validation, observability, and rollback impact were
  considered where relevant.
- The final commit history is understandable.
