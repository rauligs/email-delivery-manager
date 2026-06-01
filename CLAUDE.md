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

# context-mode — MANDATORY routing rules

You have context-mode MCP tools available. These rules are NOT optional — they protect your context window from
flooding. A single unrouted command can dump 56 KB into context and waste the entire session.

## BLOCKED commands — do NOT attempt these

### curl / wget — BLOCKED

Any Bash command containing `curl` or `wget` is intercepted and replaced with an error message. Do NOT retry.
Instead use:

- `ctx_fetch_and_index(url, source)` to fetch and index web pages
- `ctx_execute(language: "javascript", code: "const r = await fetch(...)")` to run HTTP calls in sandbox

### Inline HTTP — BLOCKED

Any Bash command containing `fetch('http`, `requests.get(`, `requests.post(`, `http.get(`, or `http.request(` is
intercepted and replaced with an error message. Do NOT retry with Bash.
Instead use:

- `ctx_execute(language, code)` to run HTTP calls in sandbox — only stdout enters context

### WebFetch — BLOCKED

WebFetch calls are denied entirely. The URL is extracted and you are told to use `ctx_fetch_and_index` instead.
Instead use:

- `ctx_fetch_and_index(url, source)` then `ctx_search(queries)` to query the indexed content

## REDIRECTED tools — use sandbox equivalents

### Bash (>20 lines output)

Bash is ONLY for: `git`, `mkdir`, `rm`, `mv`, `cd`, `ls`, `npm install`, `pip install`, and other short-output commands.
For everything else, use:

- `ctx_batch_execute(commands, queries)` — run multiple commands + search in ONE call
- `ctx_execute(language: "shell", code: "...")` — run in sandbox, only stdout enters context

### Read (for analysis)

If you are reading a file to **Edit** it → Read is correct (Edit needs content in context).
If you are reading to **analyze, explore, or summarize** → use `ctx_execute_file(path, language, code)` instead. Only
your printed summary enters context. The raw file content stays in the sandbox.

### Grep (large results)

Grep results can flood context. Use `ctx_execute(language: "shell", code: "grep ...")` to run searches in sandbox. Only
your printed summary enters context.

## Tool selection hierarchy

1. **GATHER**: `ctx_batch_execute(commands, queries)` — Primary tool. Runs all commands, auto-indexes output, returns
   search results. ONE call replaces 30+ individual calls.
2. **FOLLOW-UP**: `ctx_search(queries: ["q1", "q2", ...])` — Query indexed content. Pass ALL questions as array in ONE
   call.
3. **PROCESSING**: `ctx_execute(language, code)` | `ctx_execute_file(path, language, code)` — Sandbox execution. Only
   stdout enters context.
4. **WEB**: `ctx_fetch_and_index(url, source)` then `ctx_search(queries)` — Fetch, chunk, index, query. Raw HTML never
   enters context.
5. **INDEX**: `ctx_index(content, source)` — Store content in FTS5 knowledge base for later search.

## Subagent routing

When spawning subagents (Agent/Task tool), the routing block is automatically injected into their prompt. Bash-type
subagents are upgraded to general-purpose so they have access to MCP tools. You do NOT need to manually instruct
subagents about context-mode.

## Output constraints

- Keep responses under 500 words.
- Write artifacts (code, configs, PRDs) to FILES — never return them as inline text. Return only: file path + 1-line
  description.
- When indexing content, use descriptive source labels so others can `ctx_search(source: "label")` later.

## ctx commands

| Command       | Action                                                                                |
|---------------|---------------------------------------------------------------------------------------|
| `ctx stats`   | Call the `ctx_stats` MCP tool and display the full output verbatim                    |
| `ctx doctor`  | Call the `ctx_doctor` MCP tool, run the returned shell command, display as checklist  |
| `ctx upgrade` | Call the `ctx_upgrade` MCP tool, run the returned shell command, display as checklist |
