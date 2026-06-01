#!/bin/bash
# Ralph AFK implementation loop.
# Picks the next available issue from issues/, asks the configured developer CLI
# to implement and verify it, then commits the result itself.
#
# Safety:
# - Claude developer mode uses --permission-mode acceptEdits with a NARROW Bash
#   allowlist (git status/diff/log/add/commit, plus the configured verification
#   command). Broad patterns like `git *` or `npm *` are deliberately not
#   allowed.
# - A lock directory under the real Git dir prevents two parallel runs racing on
#   the same issues without dirtying the worktree.
# - Requires a clean worktree before each iteration. The developer agent leaves
#   verified changes unstaged; Ralph owns all git add/commit/git rm operations.
# - Stops after MAX_ITERATIONS, after 2 consecutive iterations with no visible
#   progress, or on a non-zero exit from the developer agent.
#
# Tunables (override via env):
#   VERIFY_CMD        repo verification command        (default: ./scripts/verify.sh)
#   ALLOW_DOCKER      auto | 1 | 0                     (default: auto)
#   MAX_ITERATIONS    hard ceiling on iterations       (default: 20)
#   MAX_QA_FIXES      automatic final-QA fix attempts  (default: 2)
#   QA_DIFF_MAX_BYTES max final-QA stdin payload bytes  (default: 900000)
#   DEVELOPER_AGENT   claude | gemini | codex          (default: claude)
#   QA_AGENT          claude | gemini | codex          (default: gemini)
#   DEVELOPER_MODEL   provider model id, empty=latest  (default: empty)
#   QA_MODEL          provider model id, empty=latest  (default: empty)
#   PERMISSION_MODE   Claude only: default|acceptEdits|plan (default: acceptEdits)
#   CODEX_SANDBOX     Codex dev sandbox mode           (default: danger-full-access)
#   CODEX_DEVELOPER_REASONING_EFFORT  Codex implementation/fix effort (default: medium)
#   CODEX_QA_REASONING_EFFORT         Codex QA review effort          (default: high)
#   CLAUDE_DEVELOPER_EFFORT           Claude implementation/fix effort (default: medium)
#   CLAUDE_QA_EFFORT                  Claude QA review effort          (default: high)
#
# Flags:
#   --unsafe-bypass   use --permission-mode bypassPermissions. ONLY safe in a
#                     sandboxed container/VM with no internet - see
#                     https://docs.claude.com/en/docs/claude-code/permission-modes
#                     Refuses to run unless CLAUDECODE_SANDBOX=1.

set -uo pipefail

ENV_DEVELOPER_AGENT="${DEVELOPER_AGENT-}"
ENV_QA_AGENT="${QA_AGENT-}"
ENV_DEVELOPER_MODEL="${DEVELOPER_MODEL-}"
ENV_QA_MODEL="${QA_MODEL-}"
ENV_PERMISSION_MODE="${PERMISSION_MODE-}"
ENV_CODEX_SANDBOX="${CODEX_SANDBOX-}"
ENV_CODEX_DEVELOPER_REASONING_EFFORT="${CODEX_DEVELOPER_REASONING_EFFORT-}"
ENV_CODEX_QA_REASONING_EFFORT="${CODEX_QA_REASONING_EFFORT-}"
ENV_CLAUDE_DEVELOPER_EFFORT="${CLAUDE_DEVELOPER_EFFORT-}"
ENV_CLAUDE_QA_EFFORT="${CLAUDE_QA_EFFORT-}"
ENV_MAX_ITERATIONS="${MAX_ITERATIONS-}"
ENV_MAX_QA_FIXES="${MAX_QA_FIXES-}"
ENV_QA_DIFF_MAX_BYTES="${QA_DIFF_MAX_BYTES-}"
ENV_QA_CMD="${QA_CMD-}"
ENV_VERIFY_CMD="${VERIFY_CMD-}"
ENV_ALLOW_DOCKER="${ALLOW_DOCKER-}"
ENV_DEVELOPER_AGENT_SET=0; [ "${DEVELOPER_AGENT+x}" = x ] && ENV_DEVELOPER_AGENT_SET=1
ENV_QA_AGENT_SET=0; [ "${QA_AGENT+x}" = x ] && ENV_QA_AGENT_SET=1
ENV_DEVELOPER_MODEL_SET=0; [ "${DEVELOPER_MODEL+x}" = x ] && ENV_DEVELOPER_MODEL_SET=1
ENV_QA_MODEL_SET=0; [ "${QA_MODEL+x}" = x ] && ENV_QA_MODEL_SET=1
ENV_PERMISSION_MODE_SET=0; [ "${PERMISSION_MODE+x}" = x ] && ENV_PERMISSION_MODE_SET=1
ENV_CODEX_SANDBOX_SET=0; [ "${CODEX_SANDBOX+x}" = x ] && ENV_CODEX_SANDBOX_SET=1
ENV_CODEX_DEVELOPER_REASONING_EFFORT_SET=0; [ "${CODEX_DEVELOPER_REASONING_EFFORT+x}" = x ] && ENV_CODEX_DEVELOPER_REASONING_EFFORT_SET=1
ENV_CODEX_QA_REASONING_EFFORT_SET=0; [ "${CODEX_QA_REASONING_EFFORT+x}" = x ] && ENV_CODEX_QA_REASONING_EFFORT_SET=1
ENV_CLAUDE_DEVELOPER_EFFORT_SET=0; [ "${CLAUDE_DEVELOPER_EFFORT+x}" = x ] && ENV_CLAUDE_DEVELOPER_EFFORT_SET=1
ENV_CLAUDE_QA_EFFORT_SET=0; [ "${CLAUDE_QA_EFFORT+x}" = x ] && ENV_CLAUDE_QA_EFFORT_SET=1
ENV_MAX_ITERATIONS_SET=0; [ "${MAX_ITERATIONS+x}" = x ] && ENV_MAX_ITERATIONS_SET=1
ENV_MAX_QA_FIXES_SET=0; [ "${MAX_QA_FIXES+x}" = x ] && ENV_MAX_QA_FIXES_SET=1
ENV_QA_DIFF_MAX_BYTES_SET=0; [ "${QA_DIFF_MAX_BYTES+x}" = x ] && ENV_QA_DIFF_MAX_BYTES_SET=1
ENV_QA_CMD_SET=0; [ "${QA_CMD+x}" = x ] && ENV_QA_CMD_SET=1
ENV_VERIFY_CMD_SET=0; [ "${VERIFY_CMD+x}" = x ] && ENV_VERIFY_CMD_SET=1
ENV_ALLOW_DOCKER_SET=0; [ "${ALLOW_DOCKER+x}" = x ] && ENV_ALLOW_DOCKER_SET=1

# Source .ralph.env if present (persistent config - edit it any time), then let
# one-off environment variables override it.
# shellcheck disable=SC1091
[ -f .ralph.env ] && . ./.ralph.env
[ "$ENV_DEVELOPER_AGENT_SET" -eq 1 ] && DEVELOPER_AGENT="$ENV_DEVELOPER_AGENT"
[ "$ENV_QA_AGENT_SET" -eq 1 ] && QA_AGENT="$ENV_QA_AGENT"
[ "$ENV_DEVELOPER_MODEL_SET" -eq 1 ] && DEVELOPER_MODEL="$ENV_DEVELOPER_MODEL"
[ "$ENV_QA_MODEL_SET" -eq 1 ] && QA_MODEL="$ENV_QA_MODEL"
[ "$ENV_PERMISSION_MODE_SET" -eq 1 ] && PERMISSION_MODE="$ENV_PERMISSION_MODE"
[ "$ENV_CODEX_SANDBOX_SET" -eq 1 ] && CODEX_SANDBOX="$ENV_CODEX_SANDBOX"
[ "$ENV_CODEX_DEVELOPER_REASONING_EFFORT_SET" -eq 1 ] && CODEX_DEVELOPER_REASONING_EFFORT="$ENV_CODEX_DEVELOPER_REASONING_EFFORT"
[ "$ENV_CODEX_QA_REASONING_EFFORT_SET" -eq 1 ] && CODEX_QA_REASONING_EFFORT="$ENV_CODEX_QA_REASONING_EFFORT"
[ "$ENV_CLAUDE_DEVELOPER_EFFORT_SET" -eq 1 ] && CLAUDE_DEVELOPER_EFFORT="$ENV_CLAUDE_DEVELOPER_EFFORT"
[ "$ENV_CLAUDE_QA_EFFORT_SET" -eq 1 ] && CLAUDE_QA_EFFORT="$ENV_CLAUDE_QA_EFFORT"
[ "$ENV_MAX_ITERATIONS_SET" -eq 1 ] && MAX_ITERATIONS="$ENV_MAX_ITERATIONS"
[ "$ENV_MAX_QA_FIXES_SET" -eq 1 ] && MAX_QA_FIXES="$ENV_MAX_QA_FIXES"
[ "$ENV_QA_DIFF_MAX_BYTES_SET" -eq 1 ] && QA_DIFF_MAX_BYTES="$ENV_QA_DIFF_MAX_BYTES"
[ "$ENV_QA_CMD_SET" -eq 1 ] && QA_CMD="$ENV_QA_CMD"
[ "$ENV_VERIFY_CMD_SET" -eq 1 ] && VERIFY_CMD="$ENV_VERIFY_CMD"
[ "$ENV_ALLOW_DOCKER_SET" -eq 1 ] && ALLOW_DOCKER="$ENV_ALLOW_DOCKER"

DEVELOPER_AGENT="${DEVELOPER_AGENT:-claude}"
QA_AGENT="${QA_AGENT:-gemini}"
DEVELOPER_MODEL="${DEVELOPER_MODEL:-}"
QA_MODEL="${QA_MODEL:-}"
PERMISSION_MODE="${PERMISSION_MODE:-acceptEdits}"
CODEX_SANDBOX="${CODEX_SANDBOX:-danger-full-access}"
CODEX_DEVELOPER_REASONING_EFFORT="${CODEX_DEVELOPER_REASONING_EFFORT:-medium}"
CODEX_QA_REASONING_EFFORT="${CODEX_QA_REASONING_EFFORT:-high}"
CLAUDE_DEVELOPER_EFFORT="${CLAUDE_DEVELOPER_EFFORT:-medium}"
CLAUDE_QA_EFFORT="${CLAUDE_QA_EFFORT:-high}"
MAX_ITERATIONS="${MAX_ITERATIONS:-20}"
MAX_QA_FIXES="${MAX_QA_FIXES:-2}"
QA_DIFF_MAX_BYTES="${QA_DIFF_MAX_BYTES:-900000}"
VERIFY_CMD="${VERIFY_CMD:-./scripts/verify.sh}"
ALLOW_DOCKER="${ALLOW_DOCKER:-auto}"
# Advanced override. When set, this command replaces QA_AGENT/QA_MODEL and must
# read the diff on stdin.
QA_CMD="${QA_CMD:-}"
UNSAFE_BYPASS=0

for arg in "$@"; do
  case "$arg" in
    --unsafe-bypass) UNSAFE_BYPASS=1 ;;
    *) echo "Unknown argument: $arg" >&2; exit 2 ;;
  esac
done

valid_agent() {
  case "$1" in
    claude|gemini|codex) return 0 ;;
    *) return 1 ;;
  esac
}

valid_codex_reasoning_effort() {
  case "$1" in
    low|medium|high|xhigh) return 0 ;;
    *) return 1 ;;
  esac
}

valid_claude_effort() {
  case "$1" in
    low|medium|high|xhigh|max) return 0 ;;
    *) return 1 ;;
  esac
}

valid_positive_integer() {
  case "$1" in
    ''|*[!0-9]*|0) return 1 ;;
    *) return 0 ;;
  esac
}

agent_instruction_file() {
  case "$1" in
    claude) echo "CLAUDE.md" ;;
    gemini) echo "GEMINI.md" ;;
    codex) echo "AGENTS.md" ;;
    *) return 1 ;;
  esac
}

agent_skills_dir() {
  case "$1" in
    claude) echo ".claude/skills" ;;
    gemini) echo ".gemini/skills" ;;
    codex) echo ".agents/skills" ;;
    *) return 1 ;;
  esac
}

valid_agent "$DEVELOPER_AGENT" || {
  echo "Invalid DEVELOPER_AGENT=$DEVELOPER_AGENT. Use claude, gemini, or codex." >&2
  exit 2
}
valid_agent "$QA_AGENT" || {
  echo "Invalid QA_AGENT=$QA_AGENT. Use claude, gemini, or codex." >&2
  exit 2
}
if [ "$DEVELOPER_AGENT" = "$QA_AGENT" ]; then
  echo "DEVELOPER_AGENT and QA_AGENT cannot be the same." >&2
  exit 2
fi
if [ -n "$DEVELOPER_MODEL" ] && [ -n "$QA_MODEL" ] && [ "$DEVELOPER_MODEL" = "$QA_MODEL" ]; then
  echo "DEVELOPER_MODEL and QA_MODEL cannot be the same when explicitly set." >&2
  exit 2
fi
valid_codex_reasoning_effort "$CODEX_DEVELOPER_REASONING_EFFORT" || {
  echo "Invalid CODEX_DEVELOPER_REASONING_EFFORT=$CODEX_DEVELOPER_REASONING_EFFORT. Use low, medium, high, or xhigh." >&2
  exit 2
}
valid_codex_reasoning_effort "$CODEX_QA_REASONING_EFFORT" || {
  echo "Invalid CODEX_QA_REASONING_EFFORT=$CODEX_QA_REASONING_EFFORT. Use low, medium, high, or xhigh." >&2
  exit 2
}
valid_claude_effort "$CLAUDE_DEVELOPER_EFFORT" || {
  echo "Invalid CLAUDE_DEVELOPER_EFFORT=$CLAUDE_DEVELOPER_EFFORT. Use low, medium, high, xhigh, or max." >&2
  exit 2
}
valid_claude_effort "$CLAUDE_QA_EFFORT" || {
  echo "Invalid CLAUDE_QA_EFFORT=$CLAUDE_QA_EFFORT. Use low, medium, high, xhigh, or max." >&2
  exit 2
}
valid_positive_integer "$QA_DIFF_MAX_BYTES" || {
  echo "Invalid QA_DIFF_MAX_BYTES=$QA_DIFF_MAX_BYTES. Use a positive integer byte budget." >&2
  exit 2
}

if [ "$UNSAFE_BYPASS" -eq 1 ]; then
  if [ "$DEVELOPER_AGENT" != "claude" ]; then
    echo "--unsafe-bypass is only supported for DEVELOPER_AGENT=claude." >&2
    exit 2
  fi
  if [ "${CLAUDECODE_SANDBOX:-0}" != "1" ]; then
    echo "Refusing --unsafe-bypass: set CLAUDECODE_SANDBOX=1 only inside an" >&2
    echo "isolated container/VM. See" >&2
    echo "https://docs.claude.com/en/docs/claude-code/permission-modes" >&2
    exit 2
  fi
  PERMISSION_MODE="bypassPermissions"
  echo "WARNING: bypassPermissions enabled. All safety prompts disabled."
fi

if [ "$VERIFY_CMD" = "./scripts/verify.sh" ] && [ ! -x ./scripts/verify.sh ]; then
  echo "Refusing to start: ./scripts/verify.sh is missing or not executable." >&2
  echo "Run setup-ai-workflow.sh again or create scripts/verify.sh as the repo verification contract." >&2
  exit 1
fi

# Lockfile to prevent two ralph.sh processes racing on the same issues/.
# Ask Git for the path so linked worktrees and submodules work too.
if ! LOCKDIR=$(git rev-parse --git-path ralph.lock 2>/dev/null); then
  echo "Refusing to start: not inside a git repository." >&2
  exit 1
fi
QA_BASE_FILE=$(git rev-parse --git-path ralph.qa-base)
QA_FAILS_FILE=$(git rev-parse --git-path ralph.qa-failures)
QA_REVIEW_FILE=$(git rev-parse --git-path ralph.qa-last-review)
if ! mkdir "$LOCKDIR" 2>/dev/null; then
  echo "Refusing to start: $LOCKDIR exists. Another ralph may be running." >&2
  echo "If no other process is active, remove $LOCKDIR and retry." >&2
  exit 1
fi
trap 'rmdir "$LOCKDIR" 2>/dev/null' EXIT

has_docker_reference() {
  case "${VERIFY_CMD:-}" in
    *docker*|*compose*) return 0 ;;
  esac
  if [ -f ./scripts/verify.sh ] && grep -qiE '(^|[^[:alnum:]_-])(docker|docker-compose)([[:space:]]|$)' ./scripts/verify.sh; then
    return 0
  fi
  if [ -f ./scripts/verify ] && grep -qiE '(^|[^[:alnum:]_-])(docker|docker-compose)([[:space:]]|$)' ./scripts/verify; then
    return 0
  fi
  [ -f compose.yaml ] || [ -f compose.yml ] || [ -f docker-compose.yml ] || [ -f docker-compose.yaml ]
}

docker_allowed() {
  case "$(printf '%s' "$ALLOW_DOCKER" | tr '[:upper:]' '[:lower:]')" in
    1|true|yes|on) return 0 ;;
    0|false|no|off) return 1 ;;
    auto|"") has_docker_reference ;;
    *)
      echo "Warning: invalid ALLOW_DOCKER=$ALLOW_DOCKER; expected auto, 1, or 0. Treating as 0." >&2
      return 1
      ;;
  esac
}

VERIFY_BLOCK=""
VERIFY_BLOCK="${VERIFY_BLOCK}   - Required verification: ${VERIFY_CMD}\n"

DOCKER_PROMPT=""
if docker_allowed; then
  DOCKER_PROMPT="   - The verification contract may invoke Docker / Docker Compose. Do not run Docker commands directly.\n"
fi

DEVELOPER_INSTRUCTIONS=$(agent_instruction_file "$DEVELOPER_AGENT")
QA_INSTRUCTIONS=$(agent_instruction_file "$QA_AGENT")
DEVELOPER_SKILLS_DIR=$(agent_skills_dir "$DEVELOPER_AGENT")
QA_SKILLS_DIR=$(agent_skills_dir "$QA_AGENT")

build_developer_prompt() {
  local selected_issue="$1"
  cat <<PROMPT
You are an AFK implementation agent.

0. Read ${DEVELOPER_INSTRUCTIONS} and follow it as your role instruction file.
   Use the folder-specific skills it references:
   - api/ -> ${DEVELOPER_SKILLS_DIR}/api/SKILL.md
   - background/ -> ${DEVELOPER_SKILLS_DIR}/python/SKILL.md
   - web/ -> ${DEVELOPER_SKILLS_DIR}/frontend/SKILL.md
1. Work only on this selected issue file: ${selected_issue}
   Read it first and use its acceptance criteria as the task contract.
2. Implement it using TDD (red, green, refactor).
3. Do not guess project test commands or run ad hoc verification commands
   such as pytest, npm test, cargo test, make test, or direct Docker checks.
   If the project needs those commands, the configured verification contract
   (normally scripts/verify.sh) must call them.
   Before handing the work back to Ralph, run exactly the required verification
   contract:
$(printf '%b' "$VERIFY_BLOCK")
$(printf '%b' "$DOCKER_PROMPT")
4. If verification passes:
     a. Do NOT run git add, git commit, or git rm.
     b. Do NOT edit, delete, or move the issue file.
     c. Leave the verified implementation changes unstaged in the worktree.
     d. Stop with a concise summary. Ralph will commit and close the issue.
5. Stop after this one issue so the outer loop can re-evaluate.
6. You may run read-only inspection commands needed to understand the issue and
   codebase, such as pwd, ls, find, rg, sed, cat, head, tail, wc, git status,
   git diff, git log, git rev-parse, and git branch. Do NOT run direct git add,
   git commit, git rm, test, type-check, lint, migration, package-manager, or
   Docker commands unless they are the configured verification command or are
   invoked by it. Do NOT run network installs (npm install, npx, brew, curl,
   etc.). If implementation or verification fails, revert only your own
   changes, leave the tree clean, and stop.
PROMPT
}

# Narrow allowlist for Claude. acceptEdits already covers Read/Edit/Write/Glob/
# Grep, so only Bash patterns need allowlisting. The verification command is
# added dynamically below.
ALLOWED_TOOLS=(
  "Bash(pwd)"
  "Bash(ls)"
  "Bash(ls *)"
  "Bash(find *)"
  "Bash(rg *)"
  "Bash(sed *)"
  "Bash(cat *)"
  "Bash(head *)"
  "Bash(tail *)"
  "Bash(wc *)"
  "Bash(git status)"
  "Bash(git status *)"
  "Bash(git diff)"
  "Bash(git diff *)"
  "Bash(git log)"
  "Bash(git log *)"
  "Bash(git rev-parse *)"
  "Bash(git branch)"
  "Bash(git branch *)"
  "Bash(ls issues*)"
  "Bash(ls issues/*)"
)
add_cmd_to_allowlist() {
  local cmd="$1"
  [ -z "$cmd" ] && return 0
  ALLOWED_TOOLS+=("Bash($cmd)")
}
add_cmd_to_allowlist "$VERIFY_CMD"

run_developer_agent() {
  local selected_issue="$1"
  local prompt
  prompt=$(build_developer_prompt "$selected_issue")

  case "$DEVELOPER_AGENT" in
    claude)
      local cmd=(claude)
      [ -n "$DEVELOPER_MODEL" ] && cmd+=(--model "$DEVELOPER_MODEL")
      cmd+=(--effort "$CLAUDE_DEVELOPER_EFFORT")
      cmd+=(-p "$prompt")
      if [ "$PERMISSION_MODE" = "bypassPermissions" ]; then
        cmd+=(--permission-mode bypassPermissions)
      else
        cmd+=(--permission-mode "$PERMISSION_MODE" --allowedTools "${ALLOWED_TOOLS[@]}")
      fi
      "${cmd[@]}"
      ;;
    gemini)
      local cmd=(gemini)
      [ -n "$DEVELOPER_MODEL" ] && cmd+=(--model "$DEVELOPER_MODEL")
      cmd+=(-p "$prompt")
      "${cmd[@]}"
      ;;
    codex)
      local cmd=(codex exec)
      [ -n "$DEVELOPER_MODEL" ] && cmd+=(--model "$DEVELOPER_MODEL")
      cmd+=(-c "model_reasoning_effort=\"$CODEX_DEVELOPER_REASONING_EFFORT\"")
      cmd+=(--sandbox "$CODEX_SANDBOX")
      cmd+=("$prompt")
      "${cmd[@]}"
      ;;
  esac
}

build_qa_fix_prompt() {
  local qa_base="$1"
  local failure_count="$2"
  local review_file="$3"
  local retry_note

  if [ "$failure_count" -ge "$MAX_QA_FIXES" ]; then
    retry_note="This is the final automatic developer fix attempt. If QA fails again, Ralph will stop for manual review."
  else
    retry_note="If QA fails again, Ralph will send the next QA notes back for another bounded fix attempt."
  fi

  cat <<PROMPT
You are an AFK implementation agent handling a failed final QA gate.

0. Read ${DEVELOPER_INSTRUCTIONS} and follow it as your role instruction file.
   Use the folder-specific skills it references:
   - api/ -> ${DEVELOPER_SKILLS_DIR}/api/SKILL.md
   - background/ -> ${DEVELOPER_SKILLS_DIR}/python/SKILL.md
   - web/ -> ${DEVELOPER_SKILLS_DIR}/frontend/SKILL.md
1. Review the cumulative diff under final QA, including any uncommitted
   final-QA fix worktree changes:
   git status --short
   git diff ${qa_base}
2. Read the QA notes below. This is QA failure ${failure_count}; ${retry_note}
3. Fix every valid blocker from QA. Also review nearby code and tests so the
   same class of issue is not left partially fixed.
4. Do not guess project test commands or run ad hoc verification commands
   such as pytest, npm test, cargo test, make test, or direct Docker checks.
   Before handing the work back to Ralph, run exactly the required verification
   contract:
$(printf '%b' "$VERIFY_BLOCK")
$(printf '%b' "$DOCKER_PROMPT")
5. You may run read-only inspection commands needed to understand the QA notes
   and codebase, such as pwd, ls, find, rg, sed, cat, head, tail, wc,
   git status, git diff, git log, git rev-parse, and git branch. Do NOT run
   direct git add, git commit, git rm, test, type-check, lint, migration,
   package-manager, or Docker commands unless they are the configured
   verification command or are invoked by it. Do NOT run network installs
   (npm install, npx, brew, curl, etc.).
6. If verification passes:
     a. Do NOT run git add, git commit, or git rm.
     b. Do NOT create, edit, delete, or move issue files.
     c. Leave the verified QA fixes unstaged in the worktree.
     d. Stop with a concise summary of what changed and how it addresses QA.
7. If implementation or verification fails, revert only your own changes, leave
   the tree clean, and stop.

QA notes:
PROMPT
  if [ -s "$review_file" ]; then
    sed 's/^/  /' "$review_file"
  else
    echo "  No reviewer notes were captured. Inspect the diff and fix any obvious release blockers."
  fi
}

run_qa_fix_agent() {
  local qa_base="$1"
  local failure_count="$2"
  local review_file="$3"
  local prompt
  prompt=$(build_qa_fix_prompt "$qa_base" "$failure_count" "$review_file")

  case "$DEVELOPER_AGENT" in
    claude)
      local cmd=(claude)
      [ -n "$DEVELOPER_MODEL" ] && cmd+=(--model "$DEVELOPER_MODEL")
      cmd+=(--effort "$CLAUDE_DEVELOPER_EFFORT")
      cmd+=(-p "$prompt")
      if [ "$PERMISSION_MODE" = "bypassPermissions" ]; then
        cmd+=(--permission-mode bypassPermissions)
      else
        cmd+=(--permission-mode "$PERMISSION_MODE" --allowedTools "${ALLOWED_TOOLS[@]}")
      fi
      "${cmd[@]}"
      ;;
    gemini)
      local cmd=(gemini)
      [ -n "$DEVELOPER_MODEL" ] && cmd+=(--model "$DEVELOPER_MODEL")
      cmd+=(-p "$prompt")
      "${cmd[@]}"
      ;;
    codex)
      local cmd=(codex exec)
      [ -n "$DEVELOPER_MODEL" ] && cmd+=(--model "$DEVELOPER_MODEL")
      cmd+=(-c "model_reasoning_effort=\"$CODEX_DEVELOPER_REASONING_EFFORT\"")
      cmd+=(--sandbox "$CODEX_SANDBOX")
      cmd+=("$prompt")
      "${cmd[@]}"
      ;;
  esac
}

QA_PROMPT="You are a QA Principal performing a strict final release gate.
Read ${QA_INSTRUCTIONS} and follow it as your QA Principal instruction file.
Review the cumulative diff supplied on stdin. If stdin says the diff was
truncated, inspect omitted changes directly in the repository before your
verdict. Be brutally honest. Check
correctness, missing tests, edge cases, security, authorization, data integrity,
architecture, maintainability, operations, accessibility, and performance where
relevant. Enforce these folder standards:
api/ -> ${QA_SKILLS_DIR}/api/SKILL.md,
background/ -> ${QA_SKILLS_DIR}/python/SKILL.md,
web/ -> ${QA_SKILLS_DIR}/frontend/SKILL.md. End
your response with exactly one final verdict line starting with PASS or
FAIL: <reason>."

run_qa_reviewer() {
  if [ -n "$QA_CMD" ]; then
    eval "$QA_CMD"
    return
  fi

  case "$QA_AGENT" in
    claude)
      local cmd=(claude)
      [ -n "$QA_MODEL" ] && cmd+=(--model "$QA_MODEL")
      cmd+=(--effort "$CLAUDE_QA_EFFORT")
      cmd+=(-p "$QA_PROMPT")
      "${cmd[@]}"
      ;;
    gemini)
      local cmd=(gemini)
      [ -n "$QA_MODEL" ] && cmd+=(--model "$QA_MODEL")
      cmd+=(-p "$QA_PROMPT")
      "${cmd[@]}"
      ;;
    codex)
      local cmd=(codex exec)
      [ -n "$QA_MODEL" ] && cmd+=(--model "$QA_MODEL")
      cmd+=(-c "model_reasoning_effort=\"$CODEX_QA_REASONING_EFFORT\"")
      cmd+=("$QA_PROMPT")
      "${cmd[@]}"
      ;;
  esac
}

hash_stdin() {
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 1
  else
    sha1sum
  fi
}

# Snapshot issues/, HEAD, and worktree state so a dirty tree counts as
# different from a clean tree at the same commit.
snapshot() {
  ( find issues -mindepth 1 -maxdepth 1 -print 2>/dev/null | sort
    git rev-parse HEAD 2>/dev/null
    git status --porcelain 2>/dev/null
  ) | hash_stdin | awk "{print \$1}"
}

dirty_tree() {
  git rev-parse --is-inside-work-tree >/dev/null 2>&1 || return 1
  [ -n "$(git status --porcelain 2>/dev/null)" ]
}

pick_issue() {
  local tier file
  for tier in Infrastructure "Tracer Bullet" Polishing; do
    while IFS= read -r file; do
      if grep -qiE "Priority tier.*${tier}" "$file"; then
        printf '%s\n' "$file"
        return 0
      fi
    done < <(find issues -mindepth 1 -maxdepth 1 -type f -name '*.md' -print 2>/dev/null | sort)
  done
  find issues -mindepth 1 -maxdepth 1 -type f -name '*.md' -print 2>/dev/null | sort | sed -n '1p'
}

commit_completed_issue() {
  local issue="$1"
  local slug
  slug=$(basename "$issue" .md)

  if [ ! -f "$issue" ]; then
    echo "Selected issue file is missing after developer run: $issue" >&2
    echo "The developer agent must not remove issue files; Ralph owns issue closure." >&2
    return 1
  fi

  git add -A
  git reset -q -- "$issue"
  if git diff --cached --quiet; then
    echo "Developer agent left no implementation changes to commit for $issue." >&2
    git reset -q
    return 1
  fi
  git commit -m "implement $slug"
  git rm "$issue"
  git commit -m "close $slug"
}

qa_failure_count() {
  local count
  count=$(sed -n '1p' "$QA_FAILS_FILE" 2>/dev/null || true)
  case "$count" in
    ''|*[!0-9]*) echo 0 ;;
    *) echo "$count" ;;
  esac
}

record_qa_failure() {
  local count="$1"
  local reason="$2"
  local review="$3"

  printf '%s\n' "$count" > "$QA_FAILS_FILE"
  {
    printf 'QA result: FAIL\n'
    printf 'Failure count: %s\n' "$count"
    printf 'Failure reason: %s\n' "$reason"
    printf 'Next action: Developer must fix and resubmit to QA.\n'
    printf '\nReviewer output:\n'
    printf '%s\n' "$review"
  } > "$QA_REVIEW_FILE"
}

commit_passed_qa_changes() {
  local failure_count

  if ! dirty_tree; then
    return 0
  fi

  failure_count=$(qa_failure_count)
  if [ "$failure_count" -le 0 ]; then
    echo "No recorded final QA failure; refusing to commit dirty QA changes." >&2
    return 1
  fi

  git add -A
  if git diff --cached --quiet; then
    echo "No staged final QA review changes to commit." >&2
    git reset -q
    return 1
  fi

  git commit -m "address final QA feedback $failure_count"
}

archive_active_prd() {
  local prd="prd/PRD.md"
  local archive_dir="prd/archive"
  local archive_path

  [ -f "$prd" ] || return 0

  mkdir -p "$archive_dir"
  archive_path="$archive_dir/$(date -u +%Y%m%dT%H%M%SZ)-PRD.md"
  mv "$prd" "$archive_path"
  git add -A "$prd" "$archive_path"
  git commit -m "archive completed PRD"
  echo "Archived completed PRD: $archive_path"
}

# Persist the starting commit so final QA cannot be bypassed by rerunning Ralph
# after a failed review. The baseline is cleared only after final QA passes.
init_qa_base() {
  [ -f "$QA_BASE_FILE" ] && return 0

  local head_now
  head_now=$(git rev-parse HEAD 2>/dev/null || echo "")
  if [ -z "$head_now" ]; then
    echo "Final QA baseline not captured: no HEAD commit yet."
    return 0
  fi
  printf '%s\n' "$head_now" > "$QA_BASE_FILE"
  rm -f "$QA_FAILS_FILE" "$QA_REVIEW_FILE" 2>/dev/null
}

QA_LOCKFILE_EXCLUDES=(
  ':(exclude)*package-lock.json'
  ':(exclude)*pnpm-lock.yaml'
  ':(exclude)*yarn.lock'
  ':(exclude)*.lock'
)

final_qa_diff() {
  local qa_base="$1"
  local file

  git diff "$qa_base" -- . "${QA_LOCKFILE_EXCLUDES[@]}" || return 1

  while IFS= read -r file; do
    printf '\n--- Untracked file: %s ---\n' "$file"
    if [ -f "$file" ]; then
      git diff --no-index -- /dev/null "$file" 2>/dev/null || true
    else
      printf 'Untracked non-regular path omitted from diff.\n'
    fi
  done < <(git ls-files --others --exclude-standard -- . "${QA_LOCKFILE_EXCLUDES[@]}")
}

final_qa_diff_stat() {
  local qa_base="$1"
  local untracked_files

  printf '--- git diff --stat %s -- ---\n' "$qa_base"
  git diff --stat=10000,10000 "$qa_base" -- . "${QA_LOCKFILE_EXCLUDES[@]}" || return 1

  untracked_files=$(git ls-files --others --exclude-standard -- . "${QA_LOCKFILE_EXCLUDES[@]}") || return 1
  if [ -n "$untracked_files" ]; then
    printf '\n--- Untracked files ---\n'
    printf '%s\n' "$untracked_files"
  fi
}

byte_count() {
  LC_ALL=C wc -c | awk '{print $1}'
}

print_truncated_bytes() {
  local max_bytes="$1"
  local text="$2"

  [ "$max_bytes" -gt 0 ] || return 0
  printf '%s' "$text" | LC_ALL=C head -c "$max_bytes"
}

cap_qa_payload() {
  local qa_base="$1"
  local diff_text="$2"
  local diff_bytes stat_text prefix prefix_bytes suffix suffix_bytes remaining body_bytes

  diff_bytes=$(printf '%s' "$diff_text" | byte_count)
  if [ "$diff_bytes" -le "$QA_DIFF_MAX_BYTES" ]; then
    printf '%s' "$diff_text"
    return 0
  fi

  stat_text=$(final_qa_diff_stat "$qa_base") || return 1
  prefix=$(cat <<PAYLOAD
NOTICE: Ralph truncated this final QA diff before sending it to the reviewer.
Original diff body bytes: ${diff_bytes}
QA_DIFF_MAX_BYTES: ${QA_DIFF_MAX_BYTES}

The complete diff body is not present on stdin. You have repository read access;
open omitted files directly with git status, git diff, git log, and file reads
before issuing a verdict. A truncated diff is never grounds to PASS. If you
cannot inspect omitted changes, return FAIL.

Generated lockfiles are intentionally omitted from the diff body, but dependency
manifest changes remain reviewable.

${stat_text}

--- Truncated diff body follows ---
PAYLOAD
)
  suffix=$(cat <<'PAYLOAD'

--- End of truncated diff body ---
PAYLOAD
)
  prefix_bytes=$(printf '%s' "$prefix" | byte_count)
  suffix_bytes=$(printf '%s' "$suffix" | byte_count)

  if [ "$prefix_bytes" -ge "$QA_DIFF_MAX_BYTES" ]; then
    print_truncated_bytes "$QA_DIFF_MAX_BYTES" "$prefix"
    return 0
  fi

  remaining=$((QA_DIFF_MAX_BYTES - prefix_bytes))
  printf '%s' "$prefix"

  if [ "$remaining" -le "$suffix_bytes" ]; then
    print_truncated_bytes "$remaining" "$suffix"
  else
    body_bytes=$((remaining - suffix_bytes))
    print_truncated_bytes "$body_bytes" "$diff_text"
    printf '%s' "$suffix"
  fi
}

run_final_qa() {
  [ -f "$QA_BASE_FILE" ] || {
    echo "Final QA skipped: no Ralph QA baseline was captured."
    echo "This is expected when there were no issues for Ralph to process."
    return 0
  }
  local qa_base head_now
  qa_base=$(sed -n '1p' "$QA_BASE_FILE")
  [ -z "$qa_base" ] && {
    echo "Final QA FAILED: empty QA baseline file ($QA_BASE_FILE)." >&2
    echo "Inspect or remove the file, then re-run Ralph." >&2
    return 1
  }
  if ! git cat-file -e "$qa_base^{commit}" 2>/dev/null; then
    echo "Final QA baseline is not a valid commit: $qa_base" >&2
    echo "Inspect or remove: $QA_BASE_FILE" >&2
    return 1
  fi

  while :; do
    local review_includes_worktree=0

    if dirty_tree; then
      if [ ! -s "$QA_REVIEW_FILE" ]; then
        echo "Working tree is dirty before final QA." >&2
        echo "Commit or stash existing changes, then resume Ralph." >&2
        return 1
      fi
      echo "--- Including uncommitted final QA fix changes in review. ---"
      review_includes_worktree=1
    fi

    head_now=$(git rev-parse HEAD 2>/dev/null || echo "")
    if [ "$qa_base" = "$head_now" ] && ! dirty_tree; then
      echo "Final QA skipped: no commits since loop start."
      rm -f "$QA_BASE_FILE" "$QA_FAILS_FILE" "$QA_REVIEW_FILE" 2>/dev/null
      return 0
    fi

    if [ -n "$QA_CMD" ]; then
      echo "--- Final QA review via custom QA_CMD ---"
    else
      echo "--- Final QA review via: $QA_AGENT${QA_MODEL:+ (model: $QA_MODEL)} ---"
    fi
    if [ "$review_includes_worktree" -eq 1 ]; then
      echo "--- Reviewing cumulative diff $qa_base..HEAD plus worktree changes ---"
    else
      echo "--- Reviewing cumulative diff $qa_base..HEAD ---"
    fi

    local diff_text qa_payload review review_status verdict failure_reason failures max_failures
    diff_text=$(final_qa_diff "$qa_base") || {
      echo "Unable to build final QA diff from $qa_base." >&2
      return 1
    }
    qa_payload=$(cap_qa_payload "$qa_base" "$diff_text") || {
      echo "Unable to build final QA review payload from $qa_base." >&2
      return 1
    }
    review=$(printf '%s' "$qa_payload" | run_qa_reviewer)
    review_status=$?
    [ -n "$review" ] && printf '%s\n' "$review"
    verdict=$(printf '%s\n' "$review" | tail -10)

    if [ "$review_status" -ne 0 ]; then
      failure_reason="QA reviewer command exited non-zero."
      echo "QA reviewer command failed. Treating as FAIL." >&2
    elif printf '%s\n' "$verdict" | grep -qE '^FAIL'; then
      failure_reason="QA returned a FAIL verdict."
    elif printf '%s\n' "$verdict" | grep -qE '^PASS'; then
      if dirty_tree; then
        if [ "$review_includes_worktree" -ne 1 ]; then
          echo "Working tree changed during final QA; refusing to commit unreviewed changes." >&2
          return 1
        fi
        commit_passed_qa_changes || return 1
      fi
      archive_active_prd || return 1
      rm -f "$QA_BASE_FILE" "$QA_FAILS_FILE" "$QA_REVIEW_FILE" 2>/dev/null
      echo "Final QA PASSED."
      return 0
    else
      failure_reason="QA output has no explicit PASS verdict in the last 10 lines."
      echo "Final QA output has no explicit PASS verdict in last 10 lines. Treating as FAIL." >&2
    fi

    failures=$(qa_failure_count)
    failures=$((failures + 1))
    max_failures=$((MAX_QA_FIXES + 1))
    record_qa_failure "$failures" "$failure_reason" "$review"

    if [ "$failures" -gt "$MAX_QA_FIXES" ]; then
      echo "Final QA failed $failures / $max_failures times. Stopping for manual review." >&2
      echo "Inspect with: git log $qa_base..HEAD" >&2
      return 1
    fi

    echo "--- Final QA failed $failures / $max_failures. Sending notes back to developer for fix attempt $failures / $MAX_QA_FIXES. ---"
    run_qa_fix_agent "$qa_base" "$failures" "$QA_REVIEW_FILE" || {
      echo "Developer agent exited non-zero while fixing final QA feedback. Stopping loop." >&2
      return 1
    }
  done
}

iter=0
no_progress=0
while [ "$iter" -lt "$MAX_ITERATIONS" ]; do
  if ! ls issues/*.md >/dev/null 2>&1; then
    echo "No issues remaining. Running final QA gate."
    run_final_qa || exit 1
    echo "Ralph loop complete."
    break
  fi
  if dirty_tree; then
    echo "Working tree is dirty before starting an iteration." >&2
    echo "Commit or stash existing changes, then resume Ralph." >&2
    exit 1
  fi
  init_qa_base
  iter=$((iter + 1))
  current_issue=$(pick_issue)
  if [ -z "$current_issue" ]; then
    echo "No issue file could be selected even though issues/*.md matched. Stopping." >&2
    exit 1
  fi
  echo "--- Ralph iteration $iter / $MAX_ITERATIONS (developer: $DEVELOPER_AGENT${DEVELOPER_MODEL:+, model: $DEVELOPER_MODEL}, issue: $current_issue) ---"

  before=$(snapshot)

  run_developer_agent "$current_issue" || {
    echo "Developer agent exited non-zero. Stopping loop." >&2
    exit 1
  }

  if dirty_tree; then
    commit_completed_issue "$current_issue" || {
      echo "Ralph could not commit the verified changes. Stopping for manual review." >&2
      exit 1
    }
  fi

  after=$(snapshot)
  if [ "$before" = "$after" ]; then
    no_progress=$((no_progress + 1))
    echo "No visible progress this iteration ($no_progress consecutive)."
    if [ "$no_progress" -ge 2 ]; then
      echo "Stopping: 2 consecutive iterations without progress." >&2
      exit 1
    fi
  else
    no_progress=0
  fi
done

if [ "$iter" -ge "$MAX_ITERATIONS" ]; then
  echo "Reached MAX_ITERATIONS=$MAX_ITERATIONS. Stopping." >&2
  exit 1
fi
