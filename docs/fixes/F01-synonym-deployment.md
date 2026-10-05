# F01 — Restore deployed synonym searches

Status: local fix complete (2026-10-05); live outage OPEN pending owner deploy and verification. Priority: P1. Type: investigation, then bounded remediation.

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

## Result (2026-10-05)

### Diagnosis (cause not confirmed; no host access)

Read-only GETs to the live site on 2026-10-05, no cookies, no POST:

| Request | Status | Meaning |
|---|---|---|
| `/sinonime` | 200 | PHP runs; `_lib.php`, `_syn.php` and `sinonime.php` parse and load. |
| `/api/syn.php?q=` | 200 | The fragment endpoint loads and renders the landing state. No database call. |
| `/api/syn.php?ac=1&q=` | 200, empty | Autocomplete returns before it opens a database. |
| `/sinonime?q=frumos`, `/sinonime.php?q=frumos`, `/api/syn.php?q=frumos`, `/api/syn.php?ac=1&q=fru` | 500, empty body | Every path that calls `syn_db()` fails. |
| `/api/search.php?q=zapciu` | 200 | `ui.db` and `pdo_sqlite` work on the host. |
| `/data/syn.db` | 403 | Inconclusive: Apache denies `*.db` before it checks if the file exists. |

The empty 500 body means `display_errors` is off and an exception was uncaught. The failure sits exactly
at the first `syn_db()` call. This rules out a PHP parse error, a missing PHP version feature in
`_syn.php`, a missing `pdo_sqlite`, and a general outage. Ranked hypotheses:

1. **`public/data/syn.db` is not on the host.** `*/data/*` is gitignored and `ui.db` is also a built
   artifact, so a deploy that copies tracked files or excludes `data/syn.db` ships `ui.db` only.
   Local repro: with `syn.db` absent, PDO creates a 0-byte file (if `data/` is writable) and the first
   query throws "no such table: key". Both cases are uncaught. If `data/` is writable, the host may now hold a
   0-byte `syn.db` that hides the original cause. Most likely.
2. **`syn.db` is empty, truncated, or damaged** (interrupted upload; 0-byte file from hypothesis 1).
3. **`syn.db` is not readable by the PHP user** (mode or owner after upload). `ui.db` works, so ask for
   `ls -l public/data` on the host.
4. **The host SQLite is too old for the schema.** Unlikely. The schema uses `WITHOUT ROWID` (SQLite 3.8.2,
   2013), `PRAGMA query_only` (3.8.0), plain tables and indexes. It has no STRICT, JSON, window functions,
   generated columns or table-valued pragmas. `ui.db` works on the same SQLite library.
5. **An older `syn.db` build with a different schema.** Fixed by deploying the current build.
   Rows: word 75,455; key 170,689; sense 85,762; edge 214,201; meta `build_date` 2026-08-17.
6. **Memory or time limit.** Unlikely: a `frumos` lookup peaks at 2 MB and takes ~90 ms locally.

Local facts: `syn.db` is 16,379,904 bytes, gitignored by `*/data/*`, journal mode `delete`, no WAL,
no `-wal`/`-shm` files. `_syn.php` needs PHP 8.0+ (`str_starts_with` in the new check needs 8.0;
arrow functions 7.4) and `pdo_sqlite`, `mbstring`. The documented rsync
(`rsync -av --exclude 'api/config.local.php' public/ host:~/voroave.ro/`) copies `data/syn.db`
(the `.gitignore` does not affect rsync). A git-based or file-list deploy does not.

### Change

- `_syn.php`: `SynUnavailable`; `syn_db()` now checks the extension, file existence (PDO never creates
  the file), readability and size before it opens, then checks the schema. `syn_search()` wraps the lookup;
  `syn_report_failure()` logs `[sinonime] unavailable: ...` with `error_log`, sends 503, `Retry-After: 300`,
  `Cache-Control: no-store`.
- `sinonime.php`, `api/syn.php`: show `_partials/syn_unavailable.php` (no path, SQL or trace). The page is
  `noindex` in that state. Autocomplete answers 503 with an empty body.
- `assets/syn.js`: allows htmx to swap a 503 into `#syn-result` (htmx 2 ignores 5xx by default).
- Unchanged: ranking, graph geometry, read-only behavior, no identity minting, empty query (200 landing),
  unknown word (200 not-found state while the database works).
- New `api/_syn_check.php`: CLI-only read-only host diagnostic.
- New `tests/test_sinonime_states.js`, suite "js sinonime states (F01)" in `tools/run_tests.py`.

### Owner steps

1. On the host, in the app folder, as the PHP user: `php api/_syn_check.php`. Send the output.
   Also: `ls -ln public/data` and the last lines of the PHP/Apache error log for `[sinonime]` or "syn.db".
2. Build locally if needed: `python tools/build_syn_db.py`. Expect 16,379,904 bytes and `build_date` 2026-08-17.
3. Deploy the code, keeping the server config:
   `rsync -av --exclude 'api/config.local.php' public/ you@host:~/voroave.ro/`
   If the deploy excludes ignored files, copy `public/data/syn.db` separately. Delete any 0-byte `syn.db` first.
4. Set the mode so the PHP user can read it: `chmod 644 public/data/syn.db`. Do not make `data/` world-writable.
5. Run `php api/_syn_check.php` again. All lines must say `ok`.
6. Verify live (GET only): `/sinonime?q=frumos` 200 with a graph; `/sinonime?q=văz` 200;
   `/api/syn.php?q=frumos` 200; `/api/syn.php?ac=1&q=tân` lists `tânăr`; `/sinonime?q=zzznotarealword` 200 not-found.
7. Add the `q=frumos` fragment request to the deploy smoke check; the landing page alone cannot catch this.

### Verification

Local: `python3 tools/run_tests.py --only sinonime` passes (both suites). Live: not verified; the outage stays open.
Not tested: the htmx swap of a 503 in a real browser (no browser test added); `chmod 000` fixture
is skipped when the test runs as root.
