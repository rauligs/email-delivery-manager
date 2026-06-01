---
name: python
description: Use when writing, reviewing, or maintaining Python scripts, CLI utilities, web scrapers, data extraction or ETL jobs, background workers, checkpointed automation, relational database-backed workflows, or Python tests and tooling for non-HTTP application code.
---

# Python Scripts, Background Work, and Tooling

Use this skill for Python automation, scripts, scrapers, data jobs, and durable background work. For HTTP services, prefer the API skill when it is available.

## MUST Rules

* Match the project's existing runtime, packaging, layout, linting, typing, and test conventions before introducing new tools.
* Keep retrieval, transformation, business logic, and persistence separated enough that core behavior can be tested without live networks, filesystems, or databases.
* Pass dependencies explicitly. Avoid hidden global clients, mutable module state, import-time side effects, and scripts whose effects depend on being run exactly once.
* Put every network call, database operation, queue operation, subprocess, lock acquisition, and long sleep behind an explicit timeout or deadline.
* Use context managers for files, sockets, subprocesses, database connections, transactions, and other owned resources.
* Use parameterized SQL or a mature query builder/ORM. Never build SQL by interpolating untrusted values.
* Use database transactions, unique constraints, row-level or advisory locks, or idempotency keys for jobs that can be retried or run concurrently.
* Persist checkpoints for long-running work before expensive steps and around external side effects so interrupted runs can resume without duplicating work.
* Stream or chunk large inputs and outputs. Avoid unbounded `read()`, `fetchall()`, list materialization, or in-memory joins unless the data size is capped and documented.
* Redact secrets, credentials, tokens, private records, and provider internals from logs, traces, errors, and CLI output.
* Treat generated code as a draft: review control flow, failure modes, type behavior, data boundaries, and operational impact before relying on it.

## SHOULD Defaults

* Prefer the project's pinned Python version. For new production work, choose the latest stable CPython supported by deployment and dependencies; use pre-release Python only for compatibility testing.
* Match the project's dependency manager and preserve its lockfile. For greenfield work, default to `uv` with `pyproject.toml` and a committed lockfile.
* Use Ruff for formatting and linting. For typing, follow the project's configured checker; for new typed work, default to basedpyright.
* Use `pytest` for tests. Add Hypothesis where parsers, validators, state machines, dedupe logic, or boundary-heavy transformations justify property-based coverage.
* Prefer structured logging with stable fields for job name, run ID, item ID, attempt, duration, result, and exception class.
* Use OpenTelemetry-compatible spans and metrics when the project is already instrumented; otherwise emit enough structured logs and counters to trace a run.
* Use `httpx` or the project's established HTTP client. Share client instances where appropriate, and retry only operations whose effects are replay-safe: idempotent reads, calls covered by idempotency keys, or writes guarded by uniqueness or dedupe state.
* For CLIs, use `argparse` from the standard library; reach for Click or Typer only when subcommand trees or rich help justify the dependency. Return nonzero on failure and avoid printing tracebacks to operators.
* Use standard-library primitives first for simple scripts; introduce frameworks only when they remove real operational complexity.
* Default to synchronous code. Use `asyncio` when I/O concurrency is the bottleneck, threads for bounded blocking I/O, and processes for CPU-heavy work.

## Background Job Patterns

* Make jobs idempotent: name the work item, record status transitions, and ensure a second run is a no-op for already-completed items.
* Separate scheduling from execution. The executable unit should accept explicit inputs and be testable without the scheduler.
* Capture enough state to resume: source cursor, page token, high-water mark, processed item IDs, or content hashes.
* Handle partial failure deliberately: retry transient failures with bounded backoff, quarantine poison records, and surface permanent failures for review.
* Keep external side effects behind a small adapter so tests can assert intent without calling the provider.

## Scraping and Extraction

* Prefer documented APIs over scraping when an API is available and suitable.
* Respect access limits and site policies. Identify the client clearly when the project has an established user agent or contact convention.
* Use `tenacity`, client-native retry support, or the project's equivalent for retry-with-backoff; cap attempts and total wall time, and add jitter to backoff.
* Normalize and validate extracted data at the boundary. Store raw payloads only when they are useful for audit, reprocessing, or debugging.
* Make parsers resilient to missing fields, changed markup, pagination gaps, duplicate records, and character encoding issues.

## Workflow

1. Inspect sibling scripts, package metadata, tests, and existing operational conventions.
2. Identify the execution model: one-shot script, CLI, cron job, queue worker, scraper, ETL, or reusable library function.
3. Define inputs, outputs, side effects, retry behavior, checkpoint state, and data volume limits before coding.
4. Implement the smallest clear path using existing project patterns and explicit boundaries.
5. Add focused tests for pure logic, adapters with fakes, and failure/resume behavior when the work is durable.
6. Run the relevant formatter, linter, type checker, tests, and a local smoke test supported by the project.

## Verification Pass

* Confirm the script can be rerun safely or document why it is intentionally one-shot.
* Check that timeouts, resource cleanup, logging, redaction, and checkpointing match the risk of the job.
* Exercise at least one success path and the most likely failure path.
* Run with the smallest realistic input before the full dataset.
* For database changes, verify transaction boundaries, constraints, migrations, and rollback behavior.
* For large data paths, verify memory use with representative input size or a documented cap.
