# Audit implementation handoff

Status (2026-10-05): F01–F08 are fixed locally and committed; none is deployed.
F02, F04 and F05 still need a live check after the owner deploys. F01 moved to the Sinonime project on 2026-10-06. F09 and F10 are planning deliverables for owner decision.
Each brief's `Status:` line is authoritative. Evidence was collected on 2026-10-05.
Reproduce each finding before changing code. Live state may change after this date.

These briefs are the execution queue. `docs/BACKLOG.md` holds their status and the wider backlog.
Historical plans describe earlier decisions; they do not override these briefs or `AGENTS.md`.

| Order | Brief | Priority | Dependency / shared files |
|---|---|---|---|
| 1 | F01 — Synonym deployment: moved with the synonym aid to `~/devbox/sinonime` (`docs/F01-deployment.md`) on 2026-10-06 | P1 | Tracked in that project |
| 2 | [F02 — Reliable sync](F02-sync.md) | P1 | `store.js`, sync API, sync tests |
| 3 | [F03 — Quiz spoilers](F03-quiz-spoilers.md) | P1 | Coordinate detail markup with F05 |
| 4 | [F04 — Statistics route](F04-statistics-route.md) | P2 | Navigation, canonical URLs, hosting |
| 5 | [F05 — Shared definitions](F05-shared-definitions.md) | P2 | Detail loader and renderer |
| 6 | [F06 — About preferences](F06-about-preferences.md) | P2 | Static About page |
| 7 | [F07 — Test harness](F07-test-harness.md) | P2 | Supports all briefs; own dependency files |
| 8 | [F08 — Atomic database build](F08-atomic-build.md) | P2 | Builder and permanent ID registry |
| Later | [F09 — Ranking evaluation](F09-evaluation.md) | Research | No production scoring changes |
| Later | [F10 — Recovery and backups](F10-recovery.md) | P2 planning | Decide account recovery before implementation |

F07 can start first if missing dependencies block the other acceptance checks.
F03 and F05 must agree on the answer-bearing markup before either is merged.
Do not have multiple agents edit the same checkout. Use separate branches/worktrees.
No brief authorizes a production deploy, bulk scrape, user merge, or dataset release.

## Starting prompt

```text
Implement docs/fixes/F02-sync.md in this repository.
Read AGENTS.md and docs/fixes/README.md first. Follow the brief's decisions,
scope, invariants, acceptance checks, and stopping conditions.
Use CodeGraph before locating or changing indexed code.
Reproduce the failure, implement the smallest complete fix, and run the
required checks against isolated fixtures. Do not write test data to production
or the existing private/app.db. Do not deploy or push.
Keep unrelated changes intact. Update the brief's status, its canonical backlog
entry, and docs/activity-history.md with the result and validation evidence.
If a required decision or access is missing, report the specific blocker;
continue independent authorized work. Do not guess the production root cause.
Commit the scoped result, including the local version update required by
AGENTS.md. Finish with the commit hash, changed behavior, test results,
remaining limitations, and any deployment steps requiring the owner.
```

Replace the filename with the assigned brief. Assign one brief per agent initially.

For F09 and F10, stop at the planning boundaries those briefs define.

## Review and closure

An implementer marks a task complete only when its acceptance checks pass.
Record local and live verification separately. A local patch does not close a live outage.
Record skipped tests explicitly. Include reproduction evidence for every regression test.
If deploying later, verify the affected live flow and its failure state after deployment.
Do not change corpus panels, scoring weights, share IDs, or account identity casually.

The docs reconciliation was completed with this handoff. Application fixes remain open.
