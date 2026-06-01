---
name: prd-to-issues
description: Break prd/PRD.md into independently grabbable issues using vertical slices (tracer bullets), one markdown file per issue in the issues/ directory. Trigger when the user says "break the PRD into issues" or after prd/PRD.md is finalized.
---

# PRD to Issues

Read `prd/PRD.md` and break it into independently grabbable issues using
**vertical slices** (tracer bullets). Avoid horizontal layers — do not do
"all DB, then all API, then all frontend".

Each issue must be a thin slice of functionality that crosses all layers
(DB, API, frontend) so the team gets instant feedback loops.

Save one issue per markdown file in the `issues/` directory, named
`NNN-short-slug.md` where `NNN` is a zero-padded priority number.
Each issue should contain:
- Title
- Priority tier (Infrastructure / Tracer Bullet / Polishing)
- Acceptance criteria
- Dependencies on other issues
