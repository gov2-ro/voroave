# F10 — Plan account recovery and verify backup operations

Status: proposal and runbook ready for owner decision; operational checks need access. Deliverables: [identity proposal](../recovery/identity-proposal.md), [backup runbook](../recovery/backup-runbook.md). Implementation of recovery stays blocked on the owner's product decision. Priority: P2.

## Problem and scope

The device cookie is the account. Losing it can strand annotations and lists.
One person using several devices can appear as several community voters.
The snapshot script exists, but its presence does not prove cron runs or off-machine recovery works.
Existing backlog entries cover Google OAuth, device linking, and external backups.
This brief consolidates the planning; it does not authorize user merges or a new login system.

## Deliverables and decisions

Document the current identity lifecycle, what survives lost localStorage, and what requires the cookie.
Compare a recovery code/device-link flow with OAuth. Include abuse, expiration, and user experience.
Never expose the HttpOnly device token to JavaScript or use fingerprinting as recovery.
Specify how a future merge handles conflicting annotations, list ownership, scores, and community counts.
Recommend one option, but leave implementation blocked on the owner's product decision.
Inspect backup scheduling and retention only with authorized operational access.
Specify backup coverage for `app.db`, signing keys, configuration, and permanent share-ID registry.
Use consistent snapshots, encrypted/access-controlled off-machine storage, and observable failure reporting.
Document a restore drill into a disposable environment, without replacing production data.
State recovery objectives and record measured restore results when access permits.

## Acceptance and boundary

Deliver an identity decision proposal and a backup/restore runbook.
Distinguish verified operational facts from missing access and assumptions.
No Google account connection, user consolidation, credential rotation, production restore,
new external service, or scheduled job change without the owner's authorization.
