# F13 — Definitions from dexonline's JSON feed

Status: brief ready 2026-11-13. Priority: P2. Needs no server access. Runs after the F11 rebuild.
Read `AGENTS.md` ("Filling definition gaps", "Synonyms" → the lock rules) first.

## Question

808 shortlist words have no definition; 2 of them are in `relevant` (`brodărie`, `bulucbașa`).
`scrape_definitions.py` reads dexonline's HTML page and its merged sinteză. dexonline also serves
`https://dexonline.ro/definitie/<word>/json`, which gives every dictionary's entry with its source name.
Use the feed to fill the gaps, with one definition per word, chosen by a fixed rule, and with its source kept.

## Facts measured 2026-11-10 (3 requests)

- The response is `{type, word, definitions: [{id, sourceName, internalRep, htmlRep, createDate, modDate, userNick}]}`.
  `abstract` returns 28 definitions from 23 dictionaries.
- A variant answers HTTP 301 to `/intrare/<headword>/<id>/json`. An unfollowed redirect gives an empty body.
  `brodărie` → `broderie` (21 definitions); `bulucbașa` → `bulucbaș` (30).
- The feed has no sinteză tree.
- The result holds entries for other headwords (`abstract` returns CADE `NUMĂR` and `NUME`).
- Many entries are pointers only: MDA2 `#vz# @bulucbașă@`, DEXI `v. bulucbașă`.
- The dump ships full text only for DEX '98 and DEX '96. The feed gives full text for every source.

## Decisions already made (owner, 2026-11-13)

1. **Licence: provisional use of all sources.** The owner contacts dexonline before the public launch.
   If the licence does not cover a source, the owner removes it. So the removal of one source must be one
   edit plus one rebuild. Store the source of every published definition.
2. **Store all.** Keep every definition the feed returns, locally. Publish one per word.
3. **Prefer the newest general dictionary.** If a word changed meaning, the newest meaning wins. If only an
   older dictionary defines the word, use the older one.

## Step 0 — Headword matching, no HTTP

`bulucbașa` has a DEX '98 definition under `bulucbașă`, so the dump may already hold it.
For the 808 words, look up the main headword through `EntryLexeme` (`main = 1`, as `mark_dex_variants()` does)
and check `definitions.db` for that headword. Report how many words this resolves. Do not merge anything yet.

## Step 1 — Classify the sources

Write `data/source_roles.tsv` (tracked in git, like `data/editorial.tsv`; add the `.gitignore` negation).
Columns: `source_name`, `year`, `role`, `publish`. Take `year` from `dict_sources.db` `sources_meta`.
Roles:

- `general` — an explanatory dictionary (DEX '16, DEX '09, DEXI, NODEX, DLRLC, DLRM, MDA2, CADE, Scriban, …).
- `normative` — spelling and inflection only (DOOM 2, DOOM 3, Ortografic, MDO, IVO-III).
- `thesaurus` — Sinonime, Sinonime82, Antonime.
- `specialized` — one domain (DTM, DGSSL, DTL, D.Religios, …).

`publish` is `1` for every row now (decision 1). Use `Source.sourceTypeId` from the dump as a first guess.
**Stop and show the owner the list before Step 3.**

## Step 2 — Fetch

New script `scrape_dexonline_json.py`. Rules:

- Take the same host lock as `scrape_definitions.py` (`acquire_host_lock()`, `data/.dexonline.lock`).
- Refuse `--delay` below 3. Follow redirects. Retry once on 429/503 after 30 s, as the HTML scraper does.
- Queue: the words that `scrape_definitions.py --dry-run` lists, minus the words Step 0 resolved.
- Write `data/processed/dexonline_json.db` (gitignored):
  `fetches(word PK, status, final_url, resolved_word, fetched_at)` and
  `entries(word, def_id, source_name, internal_rep, html_rep, mod_date, PRIMARY KEY(word, def_id))`.
  Keep every entry, including other headwords and pointers.
- Resume automatically; skip a word already in `fetches`. Provide `--dry-run` (no HTTP, no lock) and `--limit`.
- Run `--limit 20` first and report. The full run is about 1,000 words, about 52 minutes.

## Step 3 — Choose one definition per word

A pure function, with unit tests on the three saved responses (copy them into `tests/fixtures/`):

1. Keep entries whose headword (the first `@…@` in `internal_rep`, stress marks removed) equals the word
   or `resolved_word`.
2. Drop pointer-only entries: the body after the grammar label is only `vz`/`v.`/`V.` and a headword.
3. Keep `publish = 1` sources. Pick the `general` entry with the newest `year`.
   If there is none, pick the newest `specialized` entry. Never pick `normative` or `thesaurus`.
4. Text: `html_rep` with tags stripped and whitespace collapsed. Keep the headword line.

Report the count of chosen definitions per source and per role, and the words still without one.
List 20 random choices (word, source, first 120 characters) for the owner to read.

## Step 4 — Merge and show the source

- Add a nullable `source TEXT` column to `definitions.db` `definitions`. Existing rows stay `NULL`.
  Insert the chosen definitions with `source` set. Do not overwrite a row that already exists.
- `tools/build_ui_db.py`: carry `source` into `words.definition_source`. Drop a definition whose source has
  `publish = 0` in `data/source_roles.tsv`. This is the removal path of decision 1.
- `detail.php`: show „după <source>" under the definition when `definition_source` is set.
  `api/word.php` must still work with a `ui.db` that has no such column (the `try`/`catch` pattern).
- Run `python3 tools/run_tests.py`. Check `git diff --numstat data/word_ids.tsv` shows additions only.

## Out of scope

- Replacing definitions that already exist (dump or August scrape) with a newer dictionary. That is about
  17,000 requests. The owner decides it separately.
- `share_meta()` excerpts, the sitemap and `noindex`. See the backlog entry on indexing.
- Deploy.

## Stop and ask

- The source list in Step 1 is ready.
- A step would change the score, a seam, or `data/word_ids.tsv` other than by appending.
  (`SCORE_HAS_DEF` is 0 since 2026-11-10, so a new definition must not move a word.)
- dexonline answers with errors or rate limits on more than 5% of the first 20 requests.

## Deliver

Update `docs/BACKLOG.md` and `docs/activity-history.md`. State full or partial verification.
