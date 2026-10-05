# F07 — Make required checks reproducible and isolated

Status: complete (local, 2026-10-05). Priority: P2.
Run `python3 tools/run_tests.py`. See `docs/activity-history.md` for evidence and limits.
Limit: the quiz DOM suite (`test_ghici.js`) failed once in four full runs; F03 owns that race.
Limit: Apache rewrite rules are not tested; the runner uses the dev router.

## Evidence and target

`pytest tests -q` passed 222 tests. Unscoped pytest also collected archived Flask tests,
producing six failures. Twelve local API suites passed against isolated user storage.
The sync suite failed because its two hardcoded words are absent from the current dictionary.
The quiz DOM suite exits successfully when jsdom is absent. No project npm manifest exists.
The target is one documented command that fails when a required check fails or cannot run.

## Scope and decisions

Own test configuration, dependency manifests, a runner, fixtures, and current setup documentation.
Keep archived tests available through an explicit legacy command; exclude them from default discovery.
Declare supported Node and PHP versions and needed extensions, based on actual test requirements.
Declare jsdom and Playwright as development dependencies with a lockfile.
Do not rely on `/Users/pax/node_modules`, a shared personal venv, or a sibling checkout for web tests.
Separate minimal test dependencies from optional corpus/frequency dependencies where practical.
Document the optional editable wRodfreq dependency and its checkout requirements explicitly.
Use temporary `OTIOS_PRIVATE_DIR` and a test admin token. Never reuse `private/app.db`.
Prefer deterministic synthetic dictionary fixtures for protocol tests; do not mutate real `ui.db`.
Keep built-data integration checks distinct and require artifacts in the full acceptance command.
The strict runner must detect skipped required suites and fail with an actionable reason.
Start/stop its own PHP server, wait for readiness, and clean up on failure.
Check clean routes using the dev router. Document that Apache deployment checks remain separate.
Do not commit private keys, user databases, logs, generated corpora, or browser caches.

## Acceptance

- A documented setup works in a clean checkout using declared dependencies.
- Default Python discovery targets current tests; explicit legacy discovery remains possible.
- Missing jsdom/browser/database/admin prerequisites fail the required command clearly.
- API tests use isolated user storage; authenticated moderation checks actually run.
- Sync tests choose durable fixtures and preserve their assertions.
- The runner returns nonzero on child failure, timeout, or required skip.
- Reruns do not modify persistent user data or leave servers running.
- Run all current API/DOM/browser suites, including tooltip and footer tests.
- Report artifact-dependent tests separately from portable tests.

## Boundary

Do not repair every archived test or use this task to redesign application behavior.
Coordinate newly added behavior regressions with their owning briefs.
