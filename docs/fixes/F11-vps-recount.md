# F11 Step 4 on the VPS — corpus recount

Status: brief ready 2026-11-09. Runs on the VPS checkout (`AGENTS.md` names `/home/pax/g2-dev/otzios`).
Parent brief: [F11](F11-local-followups.md). Read `AGENTS.md` ("Logs", "Monitoring") first.

## Why

The corpus lookup set lacked `modelType='V'`, so 3,184 verb lemmas (`râde`, `țepeni`) got no Wikisource,
LUMRO or CulturaX counts. The fixed dump parser also recovers 26 `Lexeme` rows (`electricitate`, `greșală`,
`bădic`, …) that no corpus has counted. A correct count needs a full recount. `--resume` skips documents
already counted, so it cannot add these words to an existing run.

## Rules

- Never write to the live `data/processed/corpus_frequencies.db`. All counts go to `corpus_frequencies.v2.db`.
- Do not change scoring code. Do not run `validate_diachronic.py`, `make_shortlist.py` or `build_ui_db.py` here.
  Those run on the owner's Mac after the recount.
- Do not stop a running job without the owner's approval.
- Report to the session `voroave-local` with SendMessage if it is reachable; otherwise report to the owner.

## Phase 1 — read-only; then report and wait

1. Disk space first: `df -h ~` and `df -h` for the repository's partition. Run `du -sh` on
   `data/processed/corpus_frequencies.db`, on `data/processed/*.db` and on `~/.cache/huggingface`.
   The recount needs a full copy of the corpus DB, a backup copy, and room for CulturaX parquet shards.
   Report the free space against 2× the corpus DB plus the HF cache.
2. Running jobs: `cat data/logs/*.pid`, then `ps -p <pid>` for each; `crontab -l | grep -i otzios`.
3. Checkout: `git status -sb` and `git log --oneline -3`. If the working tree is clean, `git pull`
   (expect `main` at v0.10.0 or later). If it is not clean, report it and do not pull.
4. `python status.py` (venv `~/g2-dev/monitorulpreturilor/venv`): run state and token totals per corpus.
5. Inputs: `data/raw/lumro.zip`; `data/dictionaries/dex-database.sql` (size and date; the owner's copy is
   1,649,374,734 bytes, 17 May); dates of `lexemes.db` and `corpus_frequencies.db`; whether the venv has
   `huggingface_hub` and `pyarrow`.
6. `sqlite3 -readonly data/processed/lexemes.db "select count(*) from Lexeme; select count(*) from Tag;"`.

Report all six, then wait for "go" from the owner or `voroave-local`.

## Phase 2 — after "go" (revised 2026-11-09 after the Phase 1 report)

Phase 1 found: no dump on the VPS, no `lumro.zip`, a 17 MB `corpus_frequencies.db` holding `culturax_ro` only,
3.2 GB free. CulturaX streams row groups through `HfFileSystem`, so it downloads no full shards.
So the VPS recounts **CulturaX only**. Wikisource and LUMRO are recounted on the owner's Mac.

0. `git pull --ff-only` (the untracked `__MACOSX/`, `*.tar.gz`, `public.zip` do not conflict; leave them).
1. Wait for the owner to copy the refreshed lexemes DB to `data/processed/lexemes.refreshed.db`.
   Check it: `select count(*) from Lexeme` = 317,721 and `select count(*) from Tag` = 439. If not, stop.
   Then `cp data/processed/lexemes.db data/processed/lexemes.bak-2026-11-09.db` and
   `mv data/processed/lexemes.refreshed.db data/processed/lexemes.db`.
2. `cp data/processed/corpus_frequencies.db data/processed/corpus_frequencies.bak-2026-11-09.db`
   `cp data/processed/corpus_frequencies.db data/processed/corpus_frequencies.v2.db`
   In the v2 copy only, delete the `culturax_ro` rows from every table with a `corpus_name` column. `VACUUM` it.
3. Check that `python -c "import process_culturax as p; print(len(p.load_dex_words(p.LEXEMES_DB)))"` prints a
   number larger than the old lookup set (the old set lacked 3,184 `V` lemmas). Report both numbers if you can.
4. Start CulturaX in the background with `nohup`, the log in `data/logs/culturax_v2.log` and the PID in
   `data/logs/culturax_v2.pid`:
   `python process_culturax.py --db data/processed/corpus_frequencies.v2.db --resume`
   A non-default `--db` has its own checkpoint (`corpus_frequencies.v2.culturax_checkpoint.json`), so the first
   `--resume` starts from document 0. The first run stopped on network errors and needed restarts; if the process
   exits before completion, restart it with the same command (it resumes). Do not edit the old loop or checkpoint.
5. After 30 minutes, check that the checkpoint advances. Report the rate and the ETA, then stop.

## Phase 3 — after CulturaX completes (a later session)

Compare `râde`, `țepeni`, `electricitate` and the token totals (`processing_stats`) between the old DB and v2.
Totals must match within 0.1%. Report them. The owner copies v2 to the Mac, where its `culturax_ro` rows are merged
into the Mac's v2 (which has the recounted Wikisource and LUMRO). F11 Step 2 then runs again from `validate_diachronic.py`.
