# UI database build (`tools/build_ui_db.py`)

The build replaces `public/data/ui.db` all at once or not at all.

## Steps

1. Take the registry lock (`data/word_ids.tsv.lock`) and the output lock (`ui.db.lock`).
   Both are `flock` locks and fail at once when held. The kernel frees them when the process dies.
2. Delete orphan `ui.db.build-*` files from killed builds.
3. Build a candidate in a unique `ui.db.build-XXXX.tmp` in the output directory.
4. Checkpoint the WAL and switch the candidate to DELETE journal mode. It needs no sidecar files.
5. Validate: header mode, `PRAGMA integrity_check`, required tables, `words` columns and indexes,
   non-empty and at least `--min-words` (default 10,000), every row has a unique `word_id`,
   every id equals the registry, and the build is not under 50% of the previous output (`--allow-shrink`).
6. Remove empty stale `-wal`/`-shm` files of the old output. A non-empty `-wal` stops the build
   (`--discard-stale-wal` overrides). Then `os.replace` the candidate over the output and fsync the directory.

Any failure removes the temp file and leaves the previous output byte-identical.

## ID registry

`data/word_ids.tsv` stays append-only. It is not part of the atomic swap, and there is no two-file transaction.
IDs are appended while the candidate is built. When a later step fails, those IDs stay in the registry
and no database uses them. This is harmless. The next build reuses them. No ID is ever removed or changed.
Validation refuses to publish a database whose IDs differ from the registry.

## Input policy

Required for a production build (a missing file stops the build unless `--allow-missing-inputs`):
the shortlist CSV, `definitions.db`, `dict_sources.db`, `lexemes.db`, `corpus_frequencies.db`, `inflected_forms.db`.
Without one of these, a flag, hide-control or panel value would change silently.

Optional (a missing file prints a note and the section stays empty):
`diachronic_shortlist_web_validated.csv`, `synonyms.db`, `meanings.db`, `data/editorial.tsv`,
and the `wordfreq` package (zipf columns stay NULL).

The policy does not change corpus panels or scores. `rare_words_wordfreq.csv` is not read.

## Tests

`tests/test_build_atomic.py` uses tiny synthetic shortlists with temp output and temp registry paths.
Never run the builder against the default output or the real registry in a test.
