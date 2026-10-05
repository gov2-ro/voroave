# F01 — Restore deployed synonym searches

Status: open. Priority: P1. Type: investigation, then bounded remediation.

## Evidence and target

On 2026-10-05, `/sinonime` returned 200. Queries for `frumos`, `repede`, and `văz`
returned empty HTTP 500 responses. `/sinonime.php?q=frumos` and
`/api/syn.php?q=frumos` also failed. Local `tests/test_sinonime.js` passed.
The target is a working search, fragment endpoint, autocomplete, and shared URL.
The production root cause is unknown. Do not describe a missing database as confirmed.

## Scope and decisions

Inspect `public/sinonime.php`, `public/api/syn.php`, and `public/api/_syn.php`.
Inspect `tools/build_syn_db.py` and the schemas in `docs/sinonime/spec.md`.
Compare deployed files, database schema, permissions, SQLite version, and PHP extensions.
Use server logs when available. Never copy private user data into investigation artifacts.
Distinguish failure to open the database from failure in a particular SQL query.
Fix the measured cause. Keep ranking, graph geometry, and corpus definitions unchanged.
Keep the public API read-only; synonym queries must not mint user identities.
Provide a useful unavailable state instead of a blank page for operational failures.
Return an appropriate failure status. Do not disguise outages as valid empty results.
Log technical details server-side; do not expose paths, SQL, or stack traces to visitors.

## Acceptance

- Known words render results through full-page and fragment endpoints.
- An unknown word and an empty query produce intentional states.
- Autocomplete works, including Romanian diacritics.
- A direct shared URL works without JavaScript.
- Missing/unreadable/incompatible database fixtures produce the documented unavailable state.
- `tests/test_sinonime.js` passes locally against a compatible built database.
- A read-only smoke check exercises a known query, not only the landing page.
- Record production checks separately, when authorized access allows them.

## Deliverables and boundary

Deliver the cause with evidence, a scoped patch if needed, and exact deployment steps.
If server access is unavailable, deliver local diagnostics and the questions the owner must resolve.
Do not deploy, change hosting permissions, rebuild live databases, or scrape new data.
Stop for a decision if remediation changes the schema or introduces a new dependency.
