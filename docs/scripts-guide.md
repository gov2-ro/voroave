# Current scripts and local workflow

Reviewed 2026-10-05. Run commands from the repository root.
Read [the handoff queue](fixes/README.md) before assigning fixes.

## Environment and prerequisites

The application requires PHP with PDO SQLite and mbstring. It uses vanilla JS and HTMX.
Tests need Python 3 (tested with 3.14), PHP 8.1+, Node 22+ and the `sqlite3` command. `package.json` pins jsdom and Playwright.
Run `npm ci` and `npx playwright install chromium` once.
Python scripts use a local virtual environment. Existing corpus workers may use an older shared VPS environment.
`requirements.txt` is unpinned and includes optional `-e ../gov2/wrodfreq`.
That install requires the sibling checkout. The PHP app does not require wRodfreq.
`requirements-test.txt` lists the packages the tests need. Install it for tests; install `requirements.txt` only for the pipeline.
Do not assume a clean checkout contains generated databases or the 1.65GB dump.

## Extraction

Place the source dump in `data/dictionaries/` and follow each script's input flags.
Use the full dump for production artifacts; sampled relation tables cannot establish full coverage.

```bash
python extract_lexemes.py
python extract_taxonomy.py --sql data/dictionaries/dex-database.sql
python extract_inflected_forms.py
python extract_dict_sources.py
python extract_definitions.py
python create_curated_list.py
```

Outputs include `lexemes.db`, `inflected_forms.db`, `dict_sources.db`, and `definitions.db` under `data/processed/`.
Check input existence before long processing. Extractors' default dump paths can differ; inspect `--help`.

## Corpus panels

```bash
python process_wikisource.py --resume
python process_culturax.py --resume
python process_lumro.py
```

Wikisource and LUMRO form the historical panel. CulturaX forms the modern panel.
LUMRO requires its downloaded input; see [corpus expansion](corpus-expansion-plan.md).
Wikisource counts pages; LUMRO counts distinct authors for its document evidence.
CoRoLa and subtitle data are reference artifacts, excluded from production panels.
Do not integrate new corpora without measuring time span, register, independence, and provenance.
Use `python status.py` for a read-only processing overview.

## Verdicts, ranking, and dictionary artifacts

```bash
python validate_diachronic.py
python make_shortlist.py --stats
python make_shortlist.py
python extract_meanings.py
python tools/build_ui_db.py
```

Inflection aggregation is required for credible lemma judgments.
The validator currently falls back when its map is missing; do not treat that degraded output as equivalent.
The builder currently replaces its output destructively; F08 specifies a safe replacement path.
Until F08 lands, preserve the last good artifact before rebuilding.
`data/word_ids.tsv` is append-only. Verify no existing ID is removed, changed, or assigned to another word.
Never run a rebuild or ID migration merely to execute tests.

The synonym writing aid has its own generated database:

```bash
python extract_relations.py
python tools/build_syn_db.py
```

Consult [synonym specifications](sinonime/spec.md) for inputs and schema.
`public/data/ui.db` and `public/data/syn.db` are generated artifacts, not tracked source.
`validate_with_wordfreq.py` and `validate_with_wrodfreq.py` are standalone screens; neither feeds the live ranking.
The removed wordfreq recipe is retained [as historical research](archive-obsolete/wordfreq-recipe.md).

## Editorial export

```bash
python tools/export_editorial.py --list-users
python tools/export_editorial.py --user N --dry-run
python tools/export_editorial.py --user N
```

Choose the intended curator explicitly. This reads the user database at its configured location.
Test-fixture accounts must never supply production editorial choices.
Do not merge users or bypass shrink protection during routine builds.

## Local application and tests

```bash
python3 tools/run_tests.py                  # full strict check; exit 0 only if every suite ran and passed
python3 tools/run_tests.py --portable-only  # partial: suites that need no built data
python3 tools/run_tests.py --only sync -v   # one suite, with full output
php -S 127.0.0.1:8777 -t public tools/dev-router.php   # manual dev server (uses your own config)
```

The runner stages its own copy of `public/`, a temp `OTIOS_PRIVATE_DIR` and a random admin token.
It never touches `private/app.db`, `secret.key` or `public/data/*.db`, and it checks that after the run.
It stops its PHP server on success, failure, timeout and signal.
A SKIP line, a timeout or a missing prerequisite (jsdom, Chromium, `ui.db`, `syn.db`, `sqlite3`) fails the run.
The summary lists portable suites and artifact-dependent suites separately.
Default `pytest` collects `tests/` only. Run archived tests with `.venv/bin/python -m pytest archive -q`.
For a manual run of one JS suite against your own server, set `OTIOS_TEST_URL` to an isolated server.
Never point write tests at a live URL or at the default `private/` directory.
The runner does not test Apache rewrite rules.
The 2026-10-05 audit found 222 current Python passes and six failures in archived Flask discovery.

## Deployment and recovery

Deploy only `public/`, including its generated dictionary databases and Apache rules.
Keep user storage outside the web root. Exclude local configuration from uploads.
Preserve remote `app.db`, signing keys, and deployment-specific configuration.
Review `CLAUDE.md` / `AGENTS.md` deployment invariants before changes.
`php api/_backup.php` creates a consistent snapshot; scheduling and off-machine copies need operational verification.
Local checks do not close a live outage. Production smoke checks must exercise real searches and routes.
No command in this guide authorizes deployment or production user-data writes.

The old guide is retained [in the archive](archive-obsolete/scripts-guide.md).
