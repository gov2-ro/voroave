# F08 — Publish only validated UI database builds

Status: complete locally 2026-10-05 (acceptance checks pass in `tests/test_build_atomic.py`; no production rebuild was run). Priority: P2.

## Evidence and target

`tools/build_ui_db.py` unlinks an existing output before creating its replacement.
A failure loses the last good artifact and can leave a partial database at the final path.
The target is all-or-nothing replacement of the generated database, with permanent IDs preserved.

## Scope and decisions

Own the builder, narrowly required ID-registry helpers, and failure-injection tests.
Build into a unique temporary path on the output filesystem.
Keep the previous output intact until the candidate is complete and validated.
Close all connections and checkpoint WAL before replacement; publish a self-contained database.
Use atomic replacement on the same filesystem. Clean up owned temporary files on failure.
Validate integrity, required tables/columns/indexes, unique IDs, and registry consistency.
Reject an unexpectedly empty production build. Make intentionally minimal test builds explicit.
Distinguish mandatory inputs from supported optional enrichment; do not silently drop existing features.
Document the input policy rather than changing corpus panels or scores.
The ID registry remains append-only. Never renumber, remove entries, or reassign an existing ID.
Define failure behavior for registry updates separately: harmless unused appended IDs are acceptable;
an inconsistent published database is not. Do not promise a two-file atomic transaction.
Prevent concurrent builders from publishing conflicting artifacts or allocating duplicate IDs.
Do not regenerate the real ID registry during tests.

## Acceptance

- Inject failures during load, enrichment, ID assignment, and validation.
- Each failure preserves the previous output byte-for-byte and leaves it readable.
- Success replaces the output with a complete database passing `PRAGMA integrity_check`.
- The final database is readable without temporary/WAL sidecars.
- Rebuilds preserve all existing word→ID pairs and append only genuinely new words.
- A second identical build appends no IDs.
- Test concurrent-build behavior and empty-build rejection.
- Use tiny fixtures and temporary paths; no full corpus rebuild is needed for acceptance.

## Boundary

No deployment, production rebuild, schema redesign, scoring changes, or user-data migration.
