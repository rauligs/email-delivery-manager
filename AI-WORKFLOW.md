# AI Workflow

This repo is configured for a provider-selectable AI workflow that turns an idea
into a PRD, splits the PRD into independently implementable issues, then lets
Ralph work through those issues one at a time with a separate QA Principal gate.

## Flow

1. Align on the design.

   Ask the configured developer agent to use the `grill-me` skill:

   ```sh
   grill me on this idea
   ```

   or, when the project has domain docs or needs terminology/ADR updates:

   ```sh
   use the grill-with-docs skill
   ```

2. Write the PRD.

   After the design is clear:

   ```sh
   use the write-prd skill
   ```

   This replaces the active PRD at `prd/PRD.md`.

3. Split the PRD into issues.

   Ask the developer agent to use the `prd-to-issues` skill.

   This creates one markdown file per task under `issues/`, named like
   `001-short-slug.md`.

4. Review the issues.

   Before running Ralph, check that the issue files are small, ordered, and have
   clear acceptance criteria. Each issue should be a vertical slice that can be
   implemented, tested, committed, and closed independently.

5. Run Ralph.

   Commit the workflow plan first, then start from a clean worktree:

   ```sh
   git add prd/PRD.md issues/*.md
   git commit -m "plan AI workflow issues"
   git status
   ./ralph.sh
   ```

   Ralph invokes the configured developer CLI in headless mode. Each iteration
   picks one issue, asks the developer agent to implement and verify it, then
   Ralph commits the work, removes the issue file, commits that closure, and
   repeats until there are no issues left or a safety stop is hit.

   The `issues/` directory must be trackable by Git. Do not exclude it in
   `.gitignore`; Ralph removes completed issue files with `git rm`.

## Ralph Configuration

Override these with environment variables:

```sh
VERIFY_CMD="./scripts/verify.sh" ./ralph.sh
ALLOW_DOCKER=1 ./ralph.sh
DEVELOPER_AGENT=codex QA_AGENT=gemini ./ralph.sh
DEVELOPER_MODEL="" QA_MODEL="" ./ralph.sh
MAX_ITERATIONS=5 ./ralph.sh
PERMISSION_MODE=default ./ralph.sh
CODEX_SANDBOX=danger-full-access ./ralph.sh
CODEX_DEVELOPER_REASONING_EFFORT=medium ./ralph.sh
CODEX_QA_REASONING_EFFORT=high ./ralph.sh
CLAUDE_DEVELOPER_EFFORT=medium ./ralph.sh
CLAUDE_QA_EFFORT=high ./ralph.sh
MAX_QA_FIXES=2 ./ralph.sh
QA_DIFF_MAX_BYTES=900000 ./ralph.sh
```

Defaults:

- `DEVELOPER_AGENT=claude`
- `QA_AGENT=gemini`
- `DEVELOPER_MODEL=""` and `QA_MODEL=""`, which lets each CLI use its current
  default/latest model
- `PERMISSION_MODE=acceptEdits`
- `MAX_ITERATIONS=20`
- `MAX_QA_FIXES=2`, so final QA can fail twice with automatic developer fix
  attempts before a third failed QA verdict stops for manual review
- `QA_DIFF_MAX_BYTES=900000`, so large final-QA diffs are truncated before
  they reach provider CLI input limits
- `VERIFY_CMD=./scripts/verify.sh`
- `CODEX_SANDBOX=danger-full-access`, so Codex developer runs can execute the
  repo verification contract when it needs local resources such as Docker
- `CODEX_DEVELOPER_REASONING_EFFORT=medium`, used for Codex implementation and
  final-QA fix runs
- `CODEX_QA_REASONING_EFFORT=high`, used for Codex final QA review runs
- `CODEX_PLANNING_REASONING_EFFORT=high`, documented for manual Codex planning,
  PRD, and issue-creation sessions
- `CLAUDE_DEVELOPER_EFFORT=medium`, used for Claude implementation and
  final-QA fix runs
- `CLAUDE_QA_EFFORT=high`, used for Claude final QA review runs
- `CLAUDE_PLANNING_EFFORT=high`, documented for manual Claude planning, PRD,
  and issue-creation sessions
- Gemini CLI does not currently expose a reasoning-effort flag in this workflow;
  use `GEMINI_*_MODEL`-equivalent model selection through `DEVELOPER_MODEL` and
  `QA_MODEL` when Gemini needs a stronger planning or QA model.
- `ALLOW_DOCKER=auto`, which notes when verification scripts or compose files
  indicate Docker may be used by the verification contract
- Ralph allows developer agents to run read-only inspection commands such as
  `pwd`, `ls`, `find`, `rg`, `sed`, `cat`, `head`, `tail`, `wc`, and read-only
  Git commands so they can understand the issue and codebase.
- Tests, type checks, lint, migrations, package-manager commands, Docker
  commands, and network installs must not be run directly by developer agents.
  Put every required check behind `scripts/verify.sh`.

`DEVELOPER_AGENT` and `QA_AGENT` must be different (`claude`, `gemini`, or
`codex`). If `VERIFY_CMD` is unset or blank, Ralph falls back to
`./scripts/verify.sh` rather than inspecting the project and guessing how tests
should run.

### Verification contract

Every configured project gets `scripts/verify.sh`. Treat that script as the
single repo-owned command that decides whether Ralph may commit.

For simple projects it might just run `npm test`. For real projects, especially
monorepos and mixed stacks, it should run every required check across Python
workers, Node frontends, API services, database migrations, infrastructure, and
smoke tests. If verification needs containers, put the required Docker or
Docker Compose orchestration in this script. It may delegate to `make verify`,
`just verify`, `task verify`, or any other local task runner.

The script should be deterministic and require no network installs. If the
project needs targeted module checks, put that routing logic inside
`scripts/verify.sh` rather than relying on Ralph to infer every technology
boundary. Ralph supports Docker-based verification through the verification
contract; it does not ask the developer agent to run direct Docker commands
outside that contract. Set `ALLOW_DOCKER=1` to always disclose that Docker may
be used by verification, `ALLOW_DOCKER=0` to suppress that disclosure, or keep
the default `auto`.

Developer agents may use read-only inspection commands to understand the issue
and repository, including `pwd`, `ls`, `find`, `rg`, `sed`, `cat`, `head`,
`tail`, `wc`, `git status`, `git diff`, `git log`, `git rev-parse`, and
`git branch`. Any tests, type checks, lint, migrations, package-manager
commands, Docker commands, or network installs needed for verification must run
through `scripts/verify.sh`.

### Persistent config: `.ralph.env`

The setup script writes `.ralph.env` in the repo root. Ralph sources it on
startup, so anything you set there is picked up automatically. Edit it any
time to change settings persistently — no need to re-run setup. Example:

```sh
# .ralph.env
DEVELOPER_AGENT=codex
QA_AGENT=gemini
DEVELOPER_MODEL=''
QA_MODEL=''
VERIFY_CMD='./scripts/verify.sh'
CODEX_SANDBOX=danger-full-access
CODEX_DEVELOPER_REASONING_EFFORT=medium
CODEX_QA_REASONING_EFFORT=high
CODEX_PLANNING_REASONING_EFFORT=high
CLAUDE_DEVELOPER_EFFORT=medium
CLAUDE_QA_EFFORT=high
CLAUDE_PLANNING_EFFORT=high
ALLOW_DOCKER=auto
MAX_QA_FIXES=2
QA_DIFF_MAX_BYTES=900000
```

For manual planning, PRD, and issue-creation work, start the chosen provider
with its high-effort option when the CLI supports one:

```sh
codex -c model_reasoning_effort=high
claude --effort high
```

`QA_CMD` is an advanced override. Leave it empty to use `QA_AGENT` and
`QA_MODEL`. If set, it must read the diff on stdin and end with `PASS` or
`FAIL: <reason>`.

### QA review (final gate, after all issues are done)

Ralph runs the QA Principal at the end of the loop - after the last issue file
has been removed and committed and `issues/` is empty. Ralph records the
starting commit in Git's internal directory and keeps that baseline until final
QA passes, so a failed QA run is reviewed again on resume. It pipes the
cumulative diff (`git diff <qa_base>..HEAD` - every commit Ralph made since that
baseline) into the reviewer command and expects the output to end with a line
starting with `PASS` or `FAIL: <reason>`.

Final QA input is capped by `QA_DIFF_MAX_BYTES` (default: `900000`) before it is
sent to any reviewer CLI. If the cumulative diff is larger, Ralph sends a
truncation notice, the complete `git diff --stat` file list, and as much diff
body as fits under the cap. Generated lockfiles are omitted from the review diff
body; keep dependency intent in manifest files such as `package.json` or
`pyproject.toml`.

If QA fails, Ralph sends the QA notes back to the developer agent, asks it to
review the cumulative diff, fix the blockers, run the verification contract,
and leave verified changes unstaged. Ralph keeps those fixes uncommitted,
includes the worktree changes in the next QA review, and commits them only
after QA passes. By default Ralph allows two automatic developer fix attempts
after failed QA verdicts. If QA fails a third time, Ralph stops for manual
review with any QA-fix changes still uncommitted.

Verdicts:

- `PASS` line in the last 10 lines → Ralph exits cleanly.
- `FAIL` line in the last 10 lines → Ralph records the failure and either
  starts a bounded developer fix attempt or stops after the retry limit.
- No explicit `PASS` line (missing or malformed verdict) → treated as `FAIL`.
- Reviewer command exits non-zero → treated as `FAIL`.

On any failure, inspect with `git log <qa_base>..HEAD` and `git status`. The
commits stay on disk and any failed-QA fix changes stay uncommitted; you can
amend, revert, or open follow-up issues — Ralph itself never rewrites history.
Re-running `./ralph.sh` will use the same QA baseline until the final QA gate
passes. For long-lived failed QA cycles, consider resetting the baseline after
manual cleanup or running QA in smaller batches so one review does not need to
cover dozens of issues. The QA failure counter also persists with the baseline;
remove `$(git rev-parse --git-path ralph.qa-failures)` when intentionally
starting a fresh QA cycle from the same baseline.

This is a **final** gate, not a per-iteration check. Tests / type-check still
run inside each developer iteration as before; the QA reviewer only sees a diff
of work that already passed those checks.

When final QA passes, Ralph archives the active PRD by moving `prd/PRD.md` to
`prd/archive/<timestamp>-PRD.md` and committing that move. If final QA fails,
`prd/PRD.md` stays active so the failed cycle can be fixed and resumed without
mixing it with the next plan.

The reviewer CLI is invoked from `ralph.sh` directly, outside the developer
agent context, so issue text cannot steer it.

## Safety Rules

Ralph is intentionally conservative:

- It requires a clean Git worktree before each iteration.
- It stops if the developer agent leaves uncommitted changes behind.
- It uses a lock in Git's internal directory to prevent two Ralph runs from racing.
- When Claude is the developer, it uses a narrow Claude Code tool allowlist for
  Git and verification commands.
- It stops after `MAX_ITERATIONS`.
- It stops final QA remediation after `MAX_QA_FIXES` automatic developer fix
  attempts.
- It stops after two consecutive iterations with no visible progress.

`./ralph.sh --unsafe-bypass` enables Claude Code `bypassPermissions`, but it
refuses to run unless `CLAUDECODE_SANDBOX=1` is set. Only use that inside an
isolated container or VM with no internet access.

## Recovering From Stops

If Ralph stops:

1. Run `git status`.
2. Inspect any uncommitted changes.
3. Either finish and commit them manually, or revert/stash them deliberately.
4. Fix the issue file if the task was unclear. If this was a final QA failure
   after the retry limit, amend/revert/open follow-up issues as needed; the same
   cumulative diff will be re-reviewed when you run Ralph again.
5. Re-run `./ralph.sh` from a clean worktree.

If Ralph reports that its lock already exists and no Ralph process is running,
remove it:

```sh
rmdir "$(git rev-parse --git-path ralph.lock)"
```

If you want to abandon a stuck QA baseline (e.g. you've reverted all of
Ralph's commits manually and want a fresh start), remove the baseline file:

```sh
rm "$(git rev-parse --git-path ralph.qa-base)"
```

The next Ralph run will capture a new baseline from the current HEAD and clear
any stale final-QA failure count.

## Generated Files

- One developer instruction file: `CLAUDE.md`, `GEMINI.md`, or `AGENTS.md`
- One QA Principal instruction file for a different provider
- Provider-specific engineering skills:
  - Claude: `.claude/skills/{api,python,frontend}/`
  - Gemini: `.gemini/skills/{api,python,frontend}/`
  - Codex: `.agents/skills/{api,python,frontend}/`
- Provider-specific workflow skills for the developer agent:
  - Claude: `.claude/skills/`
  - Gemini: `.gemini/skills/`
  - Codex: `.agents/skills/`
- `prd/`
- `issues/`
- `scripts/verify.sh`
- `ralph.sh`
- `.ralph.env`
- `AI-WORKFLOW.md`
