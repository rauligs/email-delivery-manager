---
name: write-prd
description: Summarize the design concept reached during a grilling session into a Product Requirements Document at prd/PRD.md. Trigger when the user says "write the PRD" or "turn this into a PRD" after alignment is complete.
---

# Write PRD

Summarize the design concept reached during the current grilling session into a
single active PRD saved at `prd/PRD.md`.

If `prd/PRD.md` already exists, replace it completely with the new active PRD.
Do not append to it, preserve old sections, or merge older plan content into the
new PRD.

Include:
- Problem Statement
- Proposed Solution
- User Stories (Definition of Done)
- Implementation Decisions
- Testing Strategy
- Out of Scope (to prevent scope creep)
