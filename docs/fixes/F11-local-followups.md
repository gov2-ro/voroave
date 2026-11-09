# F11 — Local follow-ups after the 2026-11-09 fixes

Status: in progress 2026-11-09. Priority: P2. Needs no server access.
Done: Step 0 (commits; tag `v0.9.0`), Step 1 (local Sinonime files deleted), Step 4.1 (`--db` with its own checkpoint),
Step 3 ([measurement](../eval/definition-bonus.md)). Step 4: Wikisource and LUMRO recounted on the Mac into
`data/processed/corpus_frequencies.v2.db`; CulturaX runs on the VPS ([F11-vps-recount](F11-vps-recount.md)). Step 2 ran up to `extract_meanings.py` and stopped before
`build_ui_db.py` on purpose (see "Step 2 result"). Backup: `data/backup-2026-11-09/`.
Step 4.2–4.5 run on the VPS (session `vps-sonnet`; phase 1 is a read-only disk and inventory check).

## Question

The 2026-11-09 session fixed the tuple parser, the tag families and the corpus lookup set.
These fixes change data only after the pipeline runs again. Run it, measure the effect,
and clean up the Sinonime leftovers. Read `AGENTS.md` and `docs/fixes/README.md` first.

## Decisions already made

- The owner removed the synonym aid from this project. It lives in `~/devbox/sinonime`.
- The owner authorizes rebuilds of the generated artifacts listed in this brief.
- No scoring weight changes. Measure the definition bonus; do not change it.
- `data/word_ids.tsv` stays append-only. `data/editorial.tsv` is not regenerated.
- Do not regenerate the F09 spot-check sample. Do not touch `data/eval/` marks.
- Do not deploy. Server work is in [F12](F12-server-operations.md).

## Step 0 — Commit the open work

The working tree holds the 2026-11-09 fixes and the owner's `AGENTS.md`/`CLAUDE.md` change.
Commit them as two commits: the agent-instructions change, then the fixes.
Tag the second commit `v0.9.0` locally. Do not push.

## Step 1 — Remove the local Sinonime leftovers

Delete `public/data/syn.db` and `data/processed/relations.db`. Both are gitignored copies.
Keep `data/processed/scraped_synonyms_gap.csv`; `scrape_synonyms.py --input` reads it.
Run `grep -rn "syn\.db\|relations\.db\|sinonime" --include='*.py' --include='*.php' --include='*.js' .`
outside `archive/` and `docs/`. Report any live reference; remove it only if it is dead code.

## Step 2 — Refresh the dictionary artifacts

First copy every output below to `data/backup-2026-11-09/` (gitignored).
Then run from the repository root, in this order, with the full dump:

```bash
python extract_lexemes.py
python extract_taxonomy.py
python create_curated_list.py
python validate_diachronic.py
python make_shortlist.py --stats      # record the counts
python make_shortlist.py
python extract_meanings.py
python tools/build_ui_db.py
```

Outputs: `data/processed/lexemes.{csv,db}`, `forgotten_words_curated.csv`,
`forgotten_words_diachronic.csv`, `forgotten_words_shortlist.csv`, `meanings.db`, `public/data/ui.db`.

Measure and report:

- `Tag` rows: expect 439 (was 412). `Lexeme` rows: expect 317,721 (was 317,695).
- Shortlist words with a non-empty `dex_etymology`, `dex_domain`, `dex_register`: before and after.
- Seam sizes and the default-view count: before and after. Expect no seam change.
  If any word changes seam, list it and stop: that contradicts the measured claim.
- `git diff --numstat data/word_ids.tsv` shows additions only. If not, restore the backup and stop.
- `python3 tools/run_tests.py` passes against the new `ui.db`.

### Step 2 result (2026-11-09)

- `Lexeme` 317,721 rows; `Tag` 439. Shortlist taxonomy: etymology 10,636 → 11,328, domain 1,024 → 1,067,
  register 10,138 → 10,148 words.
- 68 words changed seam (`curiosity` → `relevant`). Cause: 660 words gained a definition from the 2026-08-17
  scrape, each +5 through `SCORE_HAS_DEF`, nothing else. Not caused by the parser or tag fixes.
- 7 words joined the shortlist: `bădic`, `electricitate`, `fuștel`, `greșală`, `hermeneutic`, `judecie`, `vlădic`.
  They are lexemes the old parser dropped, so the corpora never counted them, and they read as `absent`.
  `electricitate` is not a forgotten word. **Do not run `build_ui_db.py` until the corpus recount (Step 4) is in:**
  the build would give these 7 permanent ids in the append-only `data/word_ids.tsv`.
- `public/data/ui.db` and `data/word_ids.tsv` are unchanged.

## Step 3 — Measure the five-point definition bonus

`make_shortlist.score()` adds `SCORE_HAS_DEF` (5) when `has_definition = 1`.
In a scratch script, score the new diachronic CSV twice: with the bonus, and with 0.
Do not edit `make_shortlist.py`. Write nothing under `data/processed/`.
Report: words that change seam, rank shifts in the default view (median, 90th percentile, max),
and the top-50 overlap. Write the result to `docs/eval/definition-bonus.md`. The owner decides.

## Step 4 — Recount the corpora for `modelType='V'`

`--resume` skips documents already counted, so it never counts the new lemmas.
A correct recount processes every document again.

1. Done 2026-11-09: `--db PATH` on `process_wikisource.py`, `process_lumro.py`, `process_culturax.py`.
   A non-default DB gets its own checkpoint beside it (`corpus_frequencies.v2.culturax_checkpoint.json`), so
   `--resume` neither reads nor overwrites the main run's progress. Tests: `tests/test_pipeline_lookup.py` §5.
2. Copy `corpus_frequencies.db` to `data/processed/corpus_frequencies.v2.db`. Delete that copy's rows
   for `wikisource_ro`, `lumro_ro`, `culturax_ro` only. Keep `corola_ro` and `subtitle_ro`.
3. Run Wikisource and LUMRO into the copy. Check the token totals against `status.py`.
4. CulturaX takes days. Check where its parquet input is. Start it into the copy in the background,
   with its log and PID in `data/logs/` as `AGENTS.md` describes. Report the ETA and stop.
5. After CulturaX completes, compare `râde` and `țepeni` and the total token counts.
   Swap the copy in only if the totals match the old run within 0.1%. Keep the old file.
   Then repeat Step 2 from `validate_diachronic.py` on.

## Stop and ask

- A step would change a scoring weight, a spec, an invariant, or `data/word_ids.tsv` other than by appending.
- A seam changes in Step 2, or a token total differs by more than 0.1% in Step 4.
- An input is missing (the dump, the corpora, the CulturaX shards).

## Deliver

Update `docs/BACKLOG.md` ("Owner decisions and operations") and `docs/activity-history.md`
with what ran, what it measured, and what it assumed. State full or partial verification.
