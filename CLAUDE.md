# CLAUDE.md

Guidance for Claude (and humans) working in this repository.

## Project overview

Oțios identifies "forgotten" Romanian words: terms in DEX Online (the official dictionary) that have fallen out of modern usage.

- **Phase 1 — dictionary analysis.** Parse the 1.65 GB DEX Online MySQL dump into
  `lexemes.db`, `inflected_forms.db`, `dict_sources.db` and `definitions.db`, then curate
  candidates (`create_curated_list.py`).
- **Phase 2 — corpus comparison.** `process_wikisource.py` (historical) and
  `process_culturax.py` (modern) count tokens into `corpus_frequencies.db`;
  `validate_diachronic.py` rolls those counts up over inflection paradigms and assigns a
  verdict.
- **Phase 3 — scoring and split.** `make_shortlist.py` scores every candidate and splits
  the result into two seams (see **Seams** below); `tools/build_ui_db.py` builds
  `public/data/ui.db` for the PHP app.

`validate_with_wordfreq.py` still exists as a standalone screen (see
`docs/wordfreq-recipe.md`) but **feeds nothing** — the `rare_in_use` tab it used to fill
was removed on 2026-08-11. Its list has no resolution at the low end: measured over 60,000
candidates, **99.6% score exactly 0.00** because wordfreq has never heard of them, so its
lowest real scores are ordinary words (`haz` 3.31, `bețiv` 3.22) while `zapciu`, `vornic`
and `logofăt` are all 0.00 and indistinguishable. A tier defined on that band could only
ever hold common words, at any threshold. Do not wire it back into `ui.db`. The legacy Wikipedia/OSCAR branch and `search_wild.py` are in `archive/`.

**`validate_with_wrodfreq.py` (2026-09-09) is the resolution fix for the problem above,
not yet wired into anything either.** wRodfreq — the sibling project at
`../gov2/wrodfreq`, installed here as an editable dependency (`requirements.txt`) — is a
Romanian frequency table built from 5 open corpora (23.5B+2.19B+1.94B+109.6M+84.4M
tokens), specifically built to have the coverage `wordfreq` lacks for Romanian. Measured
on the same 145,358-candidate curated list: **25.7% score exactly 0 Zipf**, not 99.6% —
resolution the `rare_in_use` tier never had. It also carries `n_reliable`/`n_attesting`/
`spread` per word (spec §8.3 of `docs/wrodfreq-spec.md` in that repo) — a corroboration
count across independent corpora, not an average, which is exactly the shape
`docs/wordfreq-recipe.md` §4 argues for. Staged as a standalone CSV output
(`forgotten_words_validated_wrodfreq.csv` / `rare_words_wrodfreq.csv`), same status
`dcr_definitions.csv`/`clre_dcr_definitions.csv` had before anyone decided how to use
them — **not merged into `make_shortlist.py`'s scoring or `ui.db`** on purpose: doing
that is a real decision about how much weight a 5-corpus corroboration count should
carry against the existing historical-attestation-driven score, and isn't made here.
The two threshold defaults (3.0/3.5 Zipf) are carried over unchanged from
`validate_with_wordfreq.py` for continuity, but were calibrated for *wordfreq's* Zipf
distribution — wRodfreq's own floors run lower (e.g. its `web` source's reliability
floor is -0.67 Zipf, driven by CulturaX's 23.5B-token size), so treat them as a
starting point, not an assumption the two scales line up.

For the methodological critique (what "forgotten" should mean, corpus options): `docs/conceptual-roadmap.md` first, then `docs/corpus-options.md`.

### Two things that are easy to get backwards

1. **`Lexeme.frequency` is not a usage frequency.** It behaves like a literary-prominence
   score: `zapciu` (an obsolete Ottoman-era tax collector) is 0.96 while `internet` is
   0.88 and `pandemie` is 0.80. High values mean "well established in the written canon",
   which is why *high* DEX frequency plus corpus absence is the signature of a forgotten
   word, and *low* DEX frequency mostly means a neologism or an obscure regionalism.
2. **The two corpora differ by 1,187× in size** (Wikisource 14.3M tokens, CulturaX 17.0B).
   Any threshold expressed in per-million terms means something completely different on
   each side. Compare occurrence counts, or percentile ranks — never ppm across corpora.

## Logs

Long-running scripts log to `data/logs/` inside the repo (gitignored by `data/*`). PIDs are saved as `<script-name>.pid` in the same directory.

```
data/logs/
  culturax.log / culturax.pid
  wikisource.log / wikisource.pid
  health_check.log      # cron output from health_check.py
  audit.log             # cron output from audit.py
  alerts.log            # every alert ever fired
  health_status.json    # alert dedup state
  run_history.jsonl     # one JSON line per audit run per corpus
  quality_YYYY-MM-DD.json
```

## Environment setup

The shared venv lives at `~/g2-dev/monitorulpreturilor/venv` — activate it before running any script:

```bash
source ~/g2-dev/monitorulpreturilor/venv/bin/activate
```

To set up from scratch:
```bash
python -m venv ~/g2-dev/monitorulpreturilor/venv && source ~/g2-dev/monitorulpreturilor/venv/bin/activate
pip install -r requirements.txt
```

`requirements.txt` covers the corpus path (`datasets`) and the frequency screen
(`wordfreq`, `simplemma`).

## End-to-end pipeline

All scripts assume `cwd` is the repo root and `data/dictionaries/` + `data/processed/` exist.

**Phase 1 — extract from the dump.** Each of these streams the 1.65 GB dump once; the
last three take a few minutes each and are independent, so they can run in any order.

```bash
python extract_lexemes.py          # → lexemes.csv + lexemes.db
python extract_taxonomy.py         # → Tag/ObjectTag/… into lexemes.db (register, domain, POS)
python extract_inflected_forms.py  # → inflected_forms.db   (2.27M forms → lemma)
python extract_dict_sources.py     # → dict_sources.db      (names, years, in_current_dict)
python extract_definitions.py      # → definitions.db
python create_curated_list.py      # → forgotten_words_curated.csv
```

**Phase 2 — corpora.** Long-running; see **Monitoring** below.

```bash
python process_wikisource.py       # historical  → corpus_frequencies.db
python process_culturax.py         # modern      → corpus_frequencies.db
```

**Phase 3 — verdicts, scoring, UI.**

```bash
python validate_diachronic.py      # → forgotten_words_diachronic.csv
python make_shortlist.py           # → forgotten_words_shortlist.csv (both seams)
python make_shortlist.py --stats   # dry run: seam and tier counts only
python extract_meanings.py         # → meanings.db (full sense trees; needs the shortlist above, no HTTP)
python tools/export_editorial.py --user N   # app.db marks → data/editorial.tsv (optional)
python tools/build_ui_db.py        # → public/data/ui.db
```

`export_editorial.py` is the one step that reads the *deployed* `app.db`, so it runs
wherever that file is. `--user` is required and never defaults — the dev `app.db` carries
hundreds of test-fixture users, and a default would publish a fixture's taste as the site's
editorial line. `--list-users` shows who has annotations; `--dry-run` prints the counts and
writes nothing. It refuses to shrink the picks by more than half without `--force`, because
a mistyped `--user` reads as "this curator marked nothing" and would blank the file.

`scrape_definitions.py --merge` fills definition gaps from dexonline.ro for words the dump
has no `DefinitionSimple` row for (keep `--delay ≥ 3`; the site is community-run).

**After any rebuild, check `git diff --numstat data/word_ids.tsv` shows additions only.**
That file is what makes `?w=` share links durable, and a renumbering breaks every link
ever shared, silently. `tests/test_rescore.py` asserts it too.

**Filling definition gaps — `scrape_definitions.py`:**

`extract_definitions.py` recovers ~4.6k of the 18.3k shortlist words from the DEX MySQL dump (the dump's `DefinitionSimple` table is the source of truth — its `lexicon` column is the headword, not a dictionary identifier). The remaining ~12.8k shortlist words have no entry there and must be scraped from dexonline.ro.

```bash
python scrape_definitions.py --dry-run --limit 5         # smoke test, no HTTP
python scrape_definitions.py --limit 20 --delay 3.0      # small live run
python scrape_definitions.py --delay 3.0 --merge         # full run, ~5–7 hrs at 3s/req
python scrape_definitions.py --merge-only                # just upsert checkpoint into db
```

Output: `data/processed/scraped_definitions.csv` (columns: `word, definition, source_url, scraped_at, status`). `status ∈ {ok, not_found, error}`. With `--merge`, ok rows are `INSERT OR REPLACE`'d into `data/processed/definitions.db`. Resume is automatic: re-running skips words already in the checkpoint or in the definitions DB. Ctrl+C is safe — each row is flushed immediately. Be polite to dexonline.ro (community-run): keep `--delay ≥ 3`.

**Exporting the DCR dictionaries — `extract_dcr.py` + `scrape_dcr.py`:**

The DCR family (Dicționar de cuvinte recente) splits across the two data sources:

- **DCR2 (1997)** — 5,807 words, and it **is in the dump in full**, just not in
  `Definition` (whose `internalRep` is a 23-char stub for every source except DEX '98/'96).
  DCR2 was digitized *structured* (`Definition.structured = 1` on all its rows), and the
  structured text — senses, sub-senses and citations with their attestations — ships in the
  `Meaning` table. `extract_dcr.py` walks `Definition(sourceId=30).id →
  EntryDefinition.definitionId → entryId → TreeEntry.entryId → treeId → Meaning` and
  renders each tree (breadcrumbs kept, citations as `◊`, cross-tree `[id]` pointers
  dropped). Output: `data/processed/dcr_definitions_dump.csv` (`word, edition, definition,
  n_sources, source_ids, status`).
  **Caveat: the trees are the entry trees (the site's sinteză), which merge every
  dictionary that defines a word.** For a word only DCR2 defines, the text IS DCR2's
  entry; for shared words `source_ids` lists the other sources and the text may mix them
  (`aburi` has 15, `accept` has 19). `scrape_dcr.py` remains the faithful per-source copy
  if exact attribution is ever wanted.
- **DCR3 (2013)** — zero rows in the dump (`DCR3` appears once: its `Source` row); only
  ~183 entries are digitized on dexonline.ro so far, mostly abbreviations and symbols, and
  as of 2026-08-17 they carry **no visible definition text anywhere on that site** — the
  per-source search finds them, but no word page renders a DCR3 definition (checked on
  `biot`, `a deux`, `a due`: no `/sursa/dcr3` wrapper, no DCR3 badge in the meaning tree).
  Nothing to scrape from dexonline.ro. `scrape_dcr.py` enumerates them from
  `/definitie-dcr3/<letter>/definitii` (31 requests, cached to
  `data/processed/dcr3_words.txt`; re-run with `--refresh-words` when digitization
  progresses) and scrapes each word page for the `.defWrapper` whose `.defDetails` carries
  the `sursa:` link — matched on the link, never the headword, because a page renders every
  related entry. Its other remaining use: filling the 9 DCR2 words whose meaning trees are
  empty in the dump (done 2026-08-17, in `data/processed/dcr_definitions.csv`).
  **A full DCR3 text does exist elsewhere — see `scrape_clre_dcr.py` below.**
- **DCR (1982)** — not a source on dexonline.ro at all; only an abbreviation cited inside
  DCR2's own entries.

**A third DCR2/DCR3 source — `scrape_clre_dcr.py`, CLRE (clre.solirom.ro), not
dexonline.ro.** The Romanian Academy's Iași institute ("Alexandru Philippide") runs a
separate digitization project, CLRE, publishing both editions as static JSON+HTML on
GitLab Pages — public, no auth, no rate limit observed (this is Fastly/Cloudflare-backed
Pages hosting, not a community server, so the delay reasoning is different from every
other scraper here; see the script's docstring). **DCR3 there has 9,424 entries with real
definition text and dated press citations** (`AH1N1` cites `R.l. 9 X 09`, `G. 29 X 09`) —
the gap the paragraph above says is empty on dexonline.ro itself is filled here. DCR2 there
has 5,770 entries, same shape, but is close to (and likely redundant with) the 5,807
`extract_dcr.py` already recovers from the dump — kept anyway as a second, faithful
per-source copy, same reasoning `scrape_dcr.py` already has for its own DCR2 pass. Word
lists need no enumeration here — each edition publishes its whole headword→id index as one
`indexes/text/cross-references.json`, unlike dexonline.ro which has no bulk listing.

```bash
python scrape_clre_dcr.py --dry-run              # plan only, no HTTP
python scrape_clre_dcr.py --merge                # full run, ~15,194 entries
python scrape_clre_dcr.py --editions dcr3 --merge  # DCR3 only
```

Output: `data/processed/clre_dcr_definitions.csv` (`word, edition, entry_id, definition,
source_url, scraped_at, status`) and, with `--merge`,
`data/processed/clre_dcr_definitions.db` (`clre_dcr_definitions(word, edition, entry_id,
definition, PRIMARY KEY(word, edition, entry_id))`). **Deliberately a separate file/table
from `dcr_definitions.db`, not merged into it** — different source, and the DCR3 rows here
are real text where that table's are effectively none. Keyed on `(word, edition,
entry_id)` rather than `(word, edition)` because CLRE gives homonyms (`ATM|1|`, `ATM|2|`)
distinct entry ids sharing one normalized word; collapsing them would mean guessing which
id wins. Not yet wired into `definitions.db` or the shortlist pipeline — this is a raw
scrape artifact, same status `dcr_definitions.csv` had before anyone decided how to use it.
Full investigation and the false start (I first tested `texts/dcr2/` without the `/site/`
suffix, got a GitLab auth redirect, and wrongly concluded the whole project was
login-gated) is in `docs/BACKLOG.md`.

```bash
python extract_dcr.py                     # DCR2 from the dump, ~15 min, no HTTP
python scrape_dcr.py --dry-run            # plan only (DCR2+DCR3 word lists)
python scrape_dcr.py --limit 20           # small live run (DCR3)
```

Scrape output: `data/processed/dcr_definitions.csv` (`word, edition, definition,
source_url, scraped_at, status`) and, with `--merge`, `data/processed/dcr_definitions.db`
(`dcr_definitions(word, edition, definition, PRIMARY KEY(word, edition))`). Both artifacts
are separate from `definitions.db` on purpose — that table is the UI's
one-definition-per-word contract, and DCR is a dictionary-copy artifact. Resume is
automatic; `--delay < 1.2` is refused.

## Key data contracts

### `lexemes.db` — `Lexeme` table (`extract_lexemes.py:124-150`)

Columns the pipeline reads:
- `form` — word as it appears in DEX
- `formNoAccent` — accent-stripped form (stress marks only; diacritics are kept)
- `frequency` — DEX score 0.0–1.0. **A literary-prominence score, not a usage frequency**
  (`zapciu` 0.96 > `internet` 0.88). Treat 0.0 as missing data, not "rarest".
- `description` — part-of-speech / register (e.g. `s.f.`, `adj.`)
- `modelType`, `notes` — used by curation heuristics

### `inflected_forms.db` (`extract_inflected_forms.py`)

```
lexeme(lexeme_id PK, lemma, frequency)          317,721 rows — complete
inflected(form, lexeme_id)                      2,269,003 rows
form_lemma(form, lemma, lexeme_id, n_lemmas)    1,633,231 rows
```

The corpus processors count raw tokens, and Romanian is heavily inflected, so without this
map a lemma is only ever credited with its citation form (`înmărmuri` 317, while
`înmărmurit` alone is 5,846). `n_lemmas` is how many lemmas claim a surface form — 12% are
shared, and `validate_diachronic.aggregate_by_family` splits those by headword prominence
rather than crediting each claimant in full.

### `dict_sources.db` (`extract_dict_sources.py`)

```
dict_sources(word PK, sources, dict_count, newest_dict_year, oldest_dict_year, in_current_dict)
sources_meta(source_id PK, short_name, year, normative)
```

113 dictionaries, 108 with a usable year. `in_current_dict` = appears in something
published from `CURRENT_DICT_YEAR` (2005) on — the line between "dropped out of the
normative lexicon" and "still official Romanian, just unused". Note `normative` is set for
only 2 sources (the DOOM editions), so use `year`, not that flag.

### `forgotten_words_curated.csv` (`create_curated_list.py:166-189`)

```
word, word_no_accent, frequency, rarity_category, description, model_type, notes
```

`rarity_category ∈ {very_rare, rare, uncommon}`, bins at 0.30 and 0.50.

### `data/word_ids.tsv` — permanent share-URL ids (`tools/word_ids.py`)

`id<TAB>word`, 1-based, **append-only**. Tracked in git on purpose (`.gitignore` negates it
out of the blanket `data/*` rule) because it is the only file that makes `?w=` links
durable: `ui.db` is deleted and rebuilt on every data refresh, so an id derived from row
order or a rowid would silently repoint every link ever shared.

Three rules, all load-bearing:

1. **Never renumber.** Ids are assigned once and keep their word forever.
2. **Never remove.** A word that drops out of a later shortlist keeps its id, so old links
   to it still resolve.
3. **Only append.** `build_ui_db.py` calls `word_ids.apply_to_db()` at the end of a build,
   which numbers unseen words (sorted, for a reproducible file) and writes `words.word_id`.

`tools/migrate_ui_db_word_ids.py` backfills an already-built `ui.db` without a full rebuild.
Both are idempotent — a second run must produce a byte-identical file, and that is the
cheapest way to check the invariant holds.

The codec is `pack_words()` / `unpack_words()` in `api/_lib.php` (`"1.4z.1f2"` — version
prefix, then base36 ids, order preserved), exposed as `api/pack.php` so the browser never
carries the dictionary. `search.php` accepts `w=` and still honours the legacy plaintext
`words=`.

### `corpus_frequencies.db` (`process_corpus.py:69-105`)

```
corpus_word_frequency(id, word, corpus_name, occurrence_count, document_count, last_updated)
processing_stats(id, corpus_name, documents_processed, tokens_processed, ...)
```

`corpus_name ∈ {wikisource_ro, lumro_ro, culturax_ro, subtitle_ro}`. The **historical panel
is `wikisource_ro` + `lumro_ro`** (`HIST_CORPORA`), aggregated separately and merged by
`merge_panels()` — documents are summed *across* corpora because a Wikisource page and a
LUMRO novel are different documents, but stay a max *within* one corpus. Merging the raw
surface counts first instead would push both through a single max and lose the documents
only the smaller corpus contributes.

**LUMRO's `document_count` is distinct authors (of 111), not novels (of 175).** `hist_docs`
is read as a claim about independence, and three novels by one novelist are one writer's
vocabulary — 638 of the 1,425 words LUMRO attests came from a single author before this,
`jupâneșică` at 47 occurrences all by V.A. Urechia among them. Occurrences still sum over
every novel; only the independence claim is corrected. Wikisource keeps counting pages
because it has no author metadata — the asymmetry follows what is knowable. Pinned by
`tests/test_process_lumro.py`, since "count novels" is the obvious simplification.

`corola_lemma_frequency` is a **separate table on purpose**: its counts are per-lemma, not
per-surface-form, so it must never go through `aggregate_by_family`. See the CoRoLa gotcha
below. Words are lowercased and
NFC-normalized. Sizes are wildly asymmetric — 14.3M vs 17.0B tokens — which is why nothing
downstream compares them in ppm.

### `meanings.db` (`extract_meanings.py`) — the dump's own sense tree

Full spec: `docs/senses-plan.md`. The chain is `Tree.description --normalize()--> the
headword`, `Tree.id -> Meaning.treeId` — no `Entry`/`EntryDefinition` hop, unlike
`extract_dcr.py`. Four passes over the dump, restricted to the 18,270 shortlist words:

```
meanings(meaning_id PK, word, tree_id, parent_id, type, breadcrumb, display_order, text)
meaning_tags(meaning_id, tag)         -- from lexemes.db's ObjectTag(objectType=3)
meaning_synonyms(meaning_id, ord, word)  -- Relation.type=1 targets, sense (type=0) only
```

`type ∈ {0 sense, 1 etymology, 2 citation, 3 comment, 4 compound, 5 expression}`. A
faithful raw copy — empty-text rows, comments and all — because deciding what to drop is
`merge_senses()`'s job (below), not the extractor's; throwing rows away here would make
that decision un-revisitable without another dump scan. **41% of the shortlist (7,470
words) has no Tree/Meaning structure at all** and keeps the flat `definition` column —
that is the normal case, not degraded coverage.

**`meaning_synonyms` fills the case a first pass missed: a sense whose `internalRep` is
empty in the dump but isn't actually contentless.** `zăticni` sense `1.` has no free text
at all, yet dexonline's own page renders "Deranja, incomoda, jena, stânjeni, stingheri,
supăra, tulbura, împiedica, încurca." as that sense's definition — composed from its 9
`Relation` rows, verified id-for-id against dexonline's rendering. Passes 3–4 (`Relation`
then a second restricted `Tree` scan, since a synonym target is almost never a shortlist
word itself) resolve every sense's synonym set, not only the empty ones — a sense with
its own prose can carry synonyms too (`zăticni` sense `2.` has both). Of the 3,627
empty-text `type=0` rows across the shortlist, 3,626 have a synonym relation; only one
does not. `Relation.type = 1` is the only value read here (verified against the `zăticni`
case above); other values are unverified and out of scope — see `docs/BACKLOG.md`'s
"per-sense synonyms" entry for what settling them would take.

### `senses` / `sense_citations` (`tools/build_ui_db.py:merge_senses()`)

```sql
senses(word, ord, breadcrumb, depth, kind, text, tags, synonyms, PRIMARY KEY(word, ord))
sense_citations(word, sense_ord, ord, text, PRIMARY KEY(word, sense_ord, ord))
```

`kind ∈ {sense, compound, expression}`; `words.dex_etymon` (pipe-delimited) is filled from
the same pass — the actual etymon word (`badana` for `bidinea`), distinct from
`dex_etymology`'s language name. `synonyms` (pipe-delimited, from `meaning_synonyms`) is
set whenever DEX gives that meaning a `Relation.type=1` list — independent of whether
`text` is also set, since a sense can have both (`zăticni` sense `2.`). Three rules
`merge_senses()` enforces, all measured against the real dump rather than assumed:

- **Senses order by parsing the breadcrumb (`bc_key()`), never by sorting it as text** —
  `'10.'` sorts before `'2.'` as a string. Every `type=0` row has a non-empty, all-numeric
  breadcrumb, so `parentId` is not needed for ordering at all.
- **A sense with empty text is dropped only if it also has no synonyms, not its
  sub-senses.** Its own citations re-attach to the nearest non-empty-*or*-synonym-bearing
  ancestor by climbing `parentId`; an orphaned quote (no such ancestor anywhere up the
  chain) is dropped rather than attached to the word as a whole, which would read as
  evidence for the wrong meaning. 3,627 of 18,459 `type=0` rows have empty text; 3,626 of
  those carry a synonym relation and are kept (numbered, with a "≡ sinonime" line standing
  in for the missing prose — see `render_sense_synonyms()` in `detail.php`), leaving only
  1 row that is a genuine placeholder with nothing to show. Before the synonym pass landed
  (2026-08-18, same day as the rest of this feature — see `docs/BACKLOG.md`), all 3,627
  were dropped outright; `zăticni` sense `1.` is the case that surfaced the gap, because
  dropping it left the surviving sense numbered `2.` with no `1.` above it, which reads as
  broken rather than as "nothing to show here".
- **A word with two `Tree` rows merges both, ordered by `tree_id`, each processed and
  numbered independently before being concatenated** — sorting the union by breadcrumb
  would interleave one tree's `1., 1.1., 2.` with the other's `1., 2.` by numeric value,
  which is not what either tree meant. Breadcrumbs can legitimately repeat (`naft` shows
  `1.` twice — one tree's chemistry sense, the other's regional one with a `1.1.`
  sub-sense). Only 2 shortlist words currently have meanings in more than one tree; most of
  the 388 words with a second `Tree` row have an empty one (an unstructured duplicate
  entry), which contributes nothing and is silently absent from `senses`.

**Five invariants, all pinned by design rather than by a test that would need the dump to
check them:**

1. **`words.definition` is never touched, reformatted, or replaced.** `mark_diminutives`,
   `pointer_target` and `mark_deverbal_nouns` all pattern-match on it, and `share_meta()` /
   `share_excerpt()` build every link preview from it. Senses are additive only.
2. **`share_excerpt()` keeps reading `definition`** — a 160-character preview has no room
   for a three-sense entry.
3. **The tree is the *entry* tree — dexonline's sinteză, which merges every dictionary
   that defines a word.** A flagged variant's senses routinely carry its headword's own
   text (`sofragerie`'s tree holds `sufragerie`'s DLRLC entry) — more senses makes that
   bleed more visible, not less, so the panel's "Variantă a lui X" line renders *above*
   the senses, not below them.
4. **Meaning-level tags (`vulgar`, `figurat`, `regional`, …) stay attached to their own
   sense** — never rolled up onto `words.dex_register`. See the `dex_pos` gotcha for why a
   word-level rollup of a sense-level signal bleeds across variants.
5. **A rebuild does not touch the `words` row set**, so `data/word_ids.tsv` stays
   additions-only exactly as before — check with `git diff --numstat data/word_ids.tsv`
   anyway, per the rule at the top of this file.

`api/word.php` queries both tables in a `try`/`catch`, so a deployed `ui.db` built before
this feature landed (neither table exists) still opens the panel — flat `definition`
fallback, no error. `tools/migrate_ui_db_senses.py` back-fills an existing `ui.db` without a
full rebuild, following `tools/migrate_ui_db_dex_variants.py`'s shape.

## Seams

`make_shortlist.py` writes one CSV whose `seam` column splits it in two, because the
project is chasing two different things:

- **`relevant`** (3,499) — strong evidence of a word that was used and faded: historically
  attested, near-absent today, broadly covered by dictionaries, still in one published
  from 2005 on. **The default view is this seam minus the hide-flags below** (2,454).
- **`curiosity`** (14,771) — everything else that still qualifies as a candidate.

The split is a weighted score (`make_shortlist.score`), not a ladder of thresholds. The
signal that does the most work is **historical attestation strength**: `politeță` occurs
143 times in Wikisource, `celșag` 4. Without it the score rewards obscurity itself and the
top of the list fills with words that were never really in circulation.

### Score vs. flags — keep these apart

Six flags mark words most people will not want to see. They are **not** part of the
score and they do **not** decide the seam.

**Three of the six are one control in the UI.** `variant_like`, `archaic_spelling` and
`dex_variant` are three ways of measuring "this is another spelling of a word that is
still alive", and they share the „variante" row in the filter sheet — see **UI defaults**
below. They stay three columns here on purpose: they are built by different rules with
different failure modes, they are kept mutually disjoint at build time, and the detail
panel names the twin differently for each. Merging the *columns* would throw away the
distinction the panel needs; keeping three *rows* asked the reader to learn our method.

- `regional_only` — a DEX regional/dialectal tag *without* also being tagged old.
  `regional|învechit` is a word that died; plain `regional` is a local term.
- `variant_like` — `family_ratio ≥ 25`, where `family_ratio` is the undivided word-family
  count over the disambiguated per-lemma one. `tinereță` sits at 298×, `veșcă` at 938×,
  while a genuinely isolated rare word sits at 1×. It catches only variants that *share an
  inflectional paradigm* — phonetic respellings like `vivliotică`/`bibliotecă` have
  unrelated paradigms and are caught instead by having no current dictionary.
- `proper_noun_like` — DEX knows this spelling **only** as a capitalised headword. It must
  stay "only": flagging every collision hid ordinary words like `gheb` ("cocoașă") because
  DEX also lists the name `Gheb`. **No longer a browsing filter** — narrowing it to "only"
  left 2 words in the whole database (`sirius`, `weltanschauung`), so a default hide plus a
  toggle was a control that revealed nothing while quietly subtracting two rows. As of the
  2026-08-11 rebuild it marks **zero**: both of those words left the shortlist when the
  candidate list was regenerated, along with `chaise-longue`, `córdoba` and the other
  hyphenated compounds. The column still gates the word of the day (`index.php`) and quiz distractors
  (`api/quiz.php`), which is a different question from what a reader may browse.
- `archaic_spelling` — an obsolete *spelling* of a word that is entirely alive under a
  modern one: `situațiune`/`situație`, `sgomot`/`zgomot`, `advocat`/`avocat`. Not the same
  as `variant_like`, which keys on a shared inflectional paradigm and therefore cannot see
  a pair whose stems differ. `spelling_of` stores the modern twin, and the detail panel
  names it ("Grafie veche pentru *situație*") rather than silently dropping the row.

  **The rules are deliberately narrow and that is the design** — see
  `mark_archaic_spellings()` in `tools/build_ui_db.py` for the measured precision of each.
  Only `-țiune/-ziune/-siune → -ție/-zie/-sie`, `sb/sd/sg → zb/zd/zg`, `des+voiced → dez`
  and `adv → av` are used, each additionally requiring a named twin at least 20× more
  frequent in the modern corpus. The general-looking rules were measured and rejected:
  `e → ă` fires 2,300 times to find 69 twins and would equate `peți` with `păți`, which are
  different words. A hide-flag's false positives are invisible — the word simply is not
  there — so precision beats recall by a wide margin here. Catches 291 words, 107 of them
  in the default view.

  Do **not** widen this by flagging everything that "fell between CoRoLa and CulturaX":
  that population is 5,421 words and 61.6% of the default view, and it is full of genuine
  finds (`acaret`, `afion`, `agie`, `alișveriș`, `amploiat`). See
  `docs/corpus-expansion-plan.md`.

  The right way to widen it is the next flag, which stops guessing from the spelling.
- `dex_variant` — **the same class of word, read out of DEX's own entry structure instead
  of inferred.** `EntryLexeme` groups the lexemes of one dictionary entry and `main`
  says which of them the entry is filed under; `main = 0` is a form dexonline lists as a
  variant of that headword. 53,618 rows say so, 4,773 of them shortlist words.
  `dex_variant_of` holds the headword and the detail panel names it („Variantă a lui
  *sufragerie*, după DEX"). Catches 1,926 words, 214 of them in the default view.
  `tools/migrate_ui_db_dex_variants.py` back-fills an existing `ui.db`; the build reads
  `lexemes.db` **and** `inflected_forms.db`, which no other `mark_*` step does.

  This exists because the rejected rules in the table above were rejected for having no
  *discriminating* power, not for being wrong: `o → u` fires 1,984 times to find 124
  twins, and `sofragerie → sufragerie` is one of the 124. The relation has no such
  problem, and it reaches pairs no spelling rule could state at all — `octomvre`,
  `hiclean`, `ghinărar`.

  Three things to keep:

  1. **A form that heads an entry of its own is left alone**, even when another entry
     files it as a variant. 1,998 shortlist words are in that position, usually because
     they carry a sense DEX records separately — `momiță` is a variant of `maimuță` and
     also a sweetbread, `partită` of `partidă` and also the musical form, `băcălie` of
     `băcănie` and also the grocer's wife. Admitting them adds ~1,000 words at an
     inspected error rate near 5%, against zero questionable rows in the 200 this admits.

     **One carve-out: a word whose entire definition is „vezi X".** The justification
     above is that a self-heading form carries a sense DEX files separately; an entry
     whose whole text is a pointer is the dictionary saying it does not. 66 words were
     kept visible by this restriction alone with nothing to read when opened —
     `volintir` („vezi voluntar"), `țignal` („vezi semnal"), `contimporan`, `nuor`. The
     pointer also **names the head**, better evidence than the edit-distance pick in
     rule 3: over the 47 pointer words the relation already flagged the two agree on 46,
     and the one disagreement is DEX's („uiet" → *huiet*, not *vuiet*). It is preferred
     rather than exclusive — where the named target is as dead as the word, the
     relation's head is used instead, which is what keeps `uiet` under the living
     `vuiet`. See `pointer_target()` in `tools/build_ui_db.py`.
  2. **The headword must clear the same `TWIN_RATIO` as the spelling rules.** Without it
     the flag hides the pairs where *both* forms are dead, which is the project's own
     material rather than noise: `antereu`/`anteriu`, `amploiat`/`amploaiat`,
     `zalhana`/`zahana`, `lighioaie`/`lighioană` — 53 in the default view.

     **It is not waived for the pointer definitions either, and that is what makes the
     carve-out safe.** „vezi X" says the word has no sense of its own; it does not say X
     is alive. Gated, the 99 pointers the flag had not claimed split 31/68 — every one
     hidden points at an ordinary modern word (`voluntar` 1.38M, `semnal` 2.59M, `nor`
     261k), and every one left standing points at a word as dead as itself
     (`bejănar`→*băjenar* 138, `bălsămit`→*bălsămat* 52, `jălbar`→*jelbar* 24). Those
     eight still read „vezi X" in the default view and should: each is two finds rather
     than a dead end. Waiving the ratio would hide them *because* DEX was terse.
  3. **The two sides of that ratio are measured differently and it is not an oversight.**
     The variant is judged by its **surface** count, because what is being judged is a
     *spelling* and a spelling is one surface form: `tinereță` is written 381 times
     against `tinerețe`'s 227,064. Roll its paradigm up instead and it reads as alive at
     227,445, because a variant shares nearly every inflected form with the word it
     varies from. The headword is judged over its **whole paradigm**, because a lemma's
     usage genuinely lives there: `lăcrima` is 0 as a bare infinitive and 16,393 as a
     verb, and gating on its citation form left `lăcrăma` labelled a variant of
     `reclama` — the only other headword in its entry the corpus could count.

  It is a **separate flag from `archaic_spelling`, and the two are disjoint**:
  `mark_dex_variants()` runs second and skips anything the regex rules already claimed.
  Folding them into one flag would lose the 42 words the relation never links (`casațiune`,
  `sbor`, `deslegare` — pre-1953 orthography dexonline has not tied together); leaving them
  overlapping would mean „grafii vechi: cu" uncovers 127 words another row is still hiding.

  **Say it in the detail panel even though `archaic_spelling` could get away without.**
  `scrape_definitions.py` reads dexonline's *sinteză*, which merges a variant into its
  headword, so `sofragerie` arrives carrying `sufragerie`'s full DLRLC entry — Sadoveanu
  quote, twin's spelling in every example. 833 rows display a definition containing the
  headword and not the word. Without the line the panel reads as an ordinary find whose
  examples inexplicably spell it differently.

  **The „vezi X" definitions are read here rather than by a rule of their own**, and the
  earlier note saying they needed no rule at all was measuring the wrong thing. All 175
  of them are *linked* by the relation, which is true and was the argument — but linkage
  is not the flag: restrictions 1 and 2 then dropped 103 of them, and 21 were sitting in
  the default view with a pointer where a definition should be. The carve-out under
  restriction 1 is the fix; it catches 13 of those 21 and leaves the 8 whose target is
  equally forgotten. Do **not** promote this to a flag of its own — the pointer is one
  more way of saying „this is another spelling of a living word", which is the „variante"
  control, and the detail panel already names the twin. Catches 1,926 words (up from
  1,893), 80 of them named by their definition.
- `deverbal_like` — a noun defined as "Faptul de a X" / "Acțiunea de a X" **whose verb X
  is on the list and visible**. `zăhăială` is defined, in full, as "Faptul de a (se)
  zăhăi", and `zăhăi` is a few rows away: the noun is the same find twice.
  `deverbal_of` holds the verb, and the detail panel links to it. 149 words, 15 of them
  in the default view. `tools/migrate_ui_db_deverbal.py` back-fills an existing `ui.db`.

  **The flag is about the duplication, not about the derivation**, and the two halves of
  that sentence are both load-bearing:

  - *Not the derivation*: 563 of the 729 deverbal definitions have no verb on the list at
    all. Marking those reads as a rule about word formation and deletes the only place a
    reader would ever meet the root — `pospăială` without `pospăi`.
  - *And visible*: on the naive "verb is in the table" rule, **10 of the 25 words it
    removes from the default view have a verb that is not in the default view either** —
    `împământeni` is `regional_only`, `pospăi` is in the curiosity seam. There the noun is
    the only member of the pair anyone can see. Requiring the verb to carry no hide-flag
    and to be in the same seam or `relevant` costs 17 words and removes the whole class.

  **`mark_deverbal_nouns()` must therefore run last**, after every other `mark_*` step —
  it reads their flags. Running it earlier marks nouns whose verb turns out to be hidden a
  moment later, and nothing downstream would notice.

  No morphological check on top of the definition, deliberately: seven pairs share fewer
  than four leading characters (`usebire`/`osebi`, `oțerire`/`oțărî`, `raznă`/`răzleți`)
  and all seven are genuine. DEX asserting the derivation is better evidence than string
  similarity is.

**The score says how good the evidence is; the flags say what you would rather not look
at.** Penalising a flag in the score as well is double-counting, and it makes the flag
unappealable: when regional words cost 25 points *and* were routed out of the seam, none
could reach the relevant list, so the UI's regionalisme control had nothing to reveal on
„cu" or „doar". As it stands the relevant seam holds 440 regional and 152 variant words,
hidden until asked for. The one score penalty that remains is for a *moderate* family ratio
(4–25×), which is an evidence problem rather than a preference — the lemma's count is
being propped up by its relatives.

- `editor_demote` — **the curator read this word and set it aside.** The only signal in the
  project that is a person's judgement rather than a measured property, and the only human
  signal allowed to *subtract*. It comes from `data/editorial.tsv` — tracked in git like
  `word_ids.tsv`, written by `tools/export_editorial.py --user N` from `app.db`, folded in
  by `build_ui_db.py` (or `tools/migrate_ui_db_editorial.py` for an existing `ui.db`).

  **A file rather than a live read of `app.db`, for two reasons that both matter.** The
  build runs on a laptop while `app.db` lives on the server outside the web root, so there
  is no moment at which the builder can see production annotations. And a signal that
  removes words from what every visitor sees has to be a diff with a git history and an
  obvious undo — as a live query it is one person's clicking silently reshaping the site,
  which is exactly the objection that deferred this feature for a year.

  `editor_pick` is its twin and subtracts from nothing: it drives the ★ chip. (It also
  drove an „Alese" card on `liste.php` until 2026-08-12 — see **Lists** below.)
  **Neither is in `quality_score`**, for the same reason the four class flags are not — a
  scored-in opinion cannot be appealed.

  **Community marks never reach `ui.db`.** They are aggregated live from every user by
  `vote_counts_subquery()` (`api/_appdb.php`) and may only *reorder*, via the `populare`
  sort. Identity here is an anonymous device token, so N votes cost N cookie clears; if
  votes could subtract, hiding a word would be cheaper than publishing a list — the same
  reasoning that keeps auto-hide-after-N-reports out of list moderation. Pinned by
  `tests/test_editorial.js`.

`diminutive_like` is a fourth flag but not one of these three. **It defaults to `hide`
like the others** — `class_modes()` has always said so — and this line used to read "off by
default, so it never subtracts from what you see until you ask", which is the opposite of
what the code does and is worth a sentence because it makes every hand-written count of the
default view wrong by 123. `mark_diminutives()`
(`tools/build_ui_db.py`) sets it from the DEX definition saying "Diminutiv al lui X" (as of the last build, 458 words in total) plus nine unambiguous suffixes whose stripped stem is a real lexeme.
`-iță` is deliberately excluded: as often a feminine agent (`păstoriță`, `vorniciță`) as a
diminutive. `tools/migrate_ui_db_diminutives.py` back-fills an existing `ui.db`.

### UI defaults

`build_word_filter()` (`public/api/_lib.php`) defaults to `seam=relevant`, hides five of
the six flag classes, **demotes rather than hides the sixth**, and sorts by `populare`.
Every one is a visible control — `seam`, plus the five class rows — never a silent
exclusion, because the point of opening this up is to learn where the lines are wrong.

**Six flag columns, five rows: `variants` is one control over three of them.** See the
note at `$class_modes`; the short version is that `variant_like`, `archaic_spelling` and
`dex_variant` are three ways of measuring one thing a reader cares about, and as three
rows they read „variante vechi / grafii vechi / variante DEX" — near-synonyms in Romanian
that nobody can be expected to tell apart. Which one found a given word is a fact about
our method, and it lives in the detail panel, which names the living twin either way.

**`editorial` is the one class that does not subtract.** Its states are `back` (default) /
`show` / `only`, and `back` is applied in the ORDER BY by `demote_order_sql()`, not as a
WHERE clause — a curator-demoted word sinks to the end instead of leaving the list. That
removed an asymmetry worth keeping removed: the curator's judgement used to be the only
human signal allowed to subtract, while the community's could only reorder. Now neither
subtracts. **Sinking is not self-explaining** — measured, the first demoted word lands at
position 2,556 of 2,682, page 11 — which is exactly why the three-state control stays:
without it there would be nothing to undo. Pinned by `test_editorial.js` §2c.

**There are no per-option counts, and that was a decision** (removed 2026-08-12). The sheet
briefly showed, beside every option, how many words it would return given everything else
set — `facet_counts()` in `_lib.php`, shipped as one out-of-band `#facet-data` attribute and
applied by `applyFacetCounts()` in `app.js`. It was correct and it was cut anyway: the
numbers were only ever wired to a few groups, so the sheet read as half-instrumented, and
they cost a row. „listă" wrapped onto two lines because `relevante 2.682` and
`curiozități 12.860` no longer fit side by side — a control the rail is meant to make
scannable, made taller by the number explaining it.

Do not re-add it piecemeal. If it comes back it is all groups or none, and the wrapping has
to be solved first. Two things the removed implementation got right and a new one would
need again:

- **Each group must be counted with its own filter switched off**, via an explicit *neutral
  value*, not `unset()`. Removing a param reinstates its default, and most of these
  default to subtracting — `unset('seam')` counts curiozități against a relevante-only
  base and reports 0.
- **One query per group, not per option.** Conditional aggregation counted every option of
  a group in one pass: eight scans of an 18k-row table, 12–40 ms, rather than forty.

Git history has the whole thing (`facet_counts`, `facet_predicate_is_usable`,
`applyFacetCounts`, `.fs-count`, the `#facet-data` placeholder and the `data-facet` hooks)
if it is ever wanted back.

**Each filter section has a „?" that reveals a one-line explainer** (`fs_label()` in
`_lib.php`). A real button and paragraph rather than a `title=` tooltip: a title needs a
hover, and a phone has none — which would mean the explanation is missing on exactly the
device where an unfamiliar filter name is hardest to guess at.

**`sort=populare` blends the derived score with what people marked** —
`quality_score + 4·ln(1+votes)`, signed, rounded into bands (`VOTE_BOOST_SQL`). Bands
rather than `LN()` because SQLite's math functions are a compile-time option a shared host
may lack. **This is the default sort.** It was deliberately not, on the grounds that votes
come from anonymous device tokens — the argument that changed it is that votes can only
ever reorder, so making it the default costs at most a nudge in position, and the damping
keeps that nudge small. `search.php` falls back to `FALLBACK_SORT` when app.db cannot be
attached; that fallback matters more now that this is what a first-time visitor gets.
Two things to keep:

- **The damping is the anti-abuse measure, not a curve preference.** The `relevant` seam
  spans 92–121 with 76% of its 3,499 words inside a ten-point band, so a linear weight of
  even 5/vote lets four votes carry a word from the median to the top forty. On the ladder,
  each *doubling* of the vote count is worth about two more points — measured: `barabor`
  carries 20 ★ votes (every one of them a test fixture) and the blend moves it 92 → 104,
  well short of `văz` at 121.
- **`search.php` joins the vote counts only for this sort**, and the subquery's key column
  is aliased `vote_word` — joined as `word` it would make every unqualified `word` in
  `build_word_filter()`'s conditions ambiguous, and those conditions are shared with the
  un-joined query.

**The five class rows are one three-state control each.** Four read `hide` / `show` /
`only` („fără / cu / doar") and all four default to `hide`. The fifth, `editorial`, reads
`back` / `show` / `only` („în spate / normal / doar") and defaults to `back`, because it
demotes rather than hides — see UI defaults below.

The rail reads `regionalisme` · `variante` · `nume de acțiune` · `diminutive` ·
`respinse`. It briefly read seven rows, with `variante vechi` / `grafii vechi` /
`variante DEX` as three of them, and **that is the shape to not go back to**: three
near-synonyms in Romanian, in a 280px column that also has to hold four other rows, each
one naming *how the word was found* rather than what it is. `deverbal` is deliberately
outside the bundle — it says the word duplicates a *different* word on the list, not that
it is another spelling of the same one.

Two things a new class has to answer before it gets a row: **can it fold into `variants`**
(is it "another spelling of a living word"?), and **is there a reader who wants it on its
own**? Five rows is comfortable, seven was not, and the fix is bundling rather than a
smaller font.

**A bundled control needs the same `only` semantics as a single one.** `hide` emits one
`= 0` condition per column; `only` pushes all its columns into `$only_cols`, which is
already OR-ed across classes — so „doar variante" is the union of the three, which is
what the label promises.

**Every superseded param spelling has to keep resolving, in both halves.**
`class_mode()` (`_lib.php`) takes an `$aliases` map: `null` for an alias carrying its own
three-state value (`?spellings=only`, from when it was its own row), a mode string for a
checkbox-era `=1` flag. `applyUrlToForm()` in `app.js` carries the same list and must be
edited with it — htmx searches from *form* state on load, so a server-only mapping leaves
an old link rendering as unfiltered while behaving as filtered. `demote_order_sql()` also
goes through `class_mode()` rather than reading `$p['editorial']` itself: an ORDER BY that
silently disagrees with the WHERE is invisible.

**`seam` is a checkbox group, not a radio.** The two seams are a partition, so both ticked
already *is* what „toate" used to be; the third radio was a name for a state the other two
could express and had to be kept in step with them. It reads through `parse_multi()` like
`verdict`/`tier`/`pos`. One consequence: its default is 1-of-2, not all-of-2, so
`groupIsDefault()` in `app.js` needs `URL_GROUP_DEFAULTS` — otherwise every URL carries
`?seam=relevant` and the chip bar claims a filter nobody set.

Adding a class is three lines in `app.js` rather than nine, because `CLASS_PARAMS` is
concatenated into both URL arrays *and* both tab guards. That is what the array is for;
keep new classes going through it rather than adding literals. **It holds one entry per
control, not per column** — `variants` appears once and covers three flags, because what
this array describes is the set of radios in the form.

Two things to preserve when touching these:

1. **Class filters are radios, not checkboxes, and that is what makes them uniform.** As
   checkboxes the polarity *had* to differ per class: an unchecked box is not submitted, so
   a class hidden by default needed `show_x=1` while one shown by default needed
   `hide_x=1` — and the sheet ended up with three „arată X" rows and two „ascunde X" rows
   that read as one set of controls and were not. A radio always submits, so the default
   can move without the wording following it. Two consequences: each param needs an entry
   in `URL_PARAM_DEFAULTS`, and the legacy `show_*=1` / `hide_diminutives=1` links must
   keep mapping — in `build_word_filter()` **and** in `applyUrlToForm()`, since htmx
   searches from form state on load and a server-only mapping leaves an old link rendering
   as filtered while behaving as if it were not.
   **There are no tab-specific controls any more, and that is worth keeping.** There used
   to be two tabs, so three sections had to be shown or hidden on `word_tier` and gated in
   *three* places kept in step by hand. It was wrong in all three on any deep link —
   `applyUrlToForm()` changes the radios without dispatching `change`, and the gate ran at
   script-eval time, so `?word_tier=rare_in_use` rendered the other tab's controls. That
   is a fourth place nobody had listed: the **initial** state, as distinct from the change
   handler. Every filter added while that existed also had to decide whether it was
   tab-specific. One list needs none of it — do not reintroduce a tab without re-reading
   this paragraph.
2. **Every filter needs registering in `public/assets/app.js` too**, or it works but the
   URL never reflects it and the state is unshareable: add it to `AF_SPECS` (the chip) and
   to the read/write arrays in `applyUrlToForm` / the URL writer — **there are two arrays,
   one per direction, and missing the writer is the silent half**. A default value goes in
   `URL_PARAM_DEFAULTS` so it is omitted from the URL when unchanged.
3. **None of it applies to a search or a playlist.** `search.php`, `random.php` and
   `feed.php` all scope through one helper, `word_scope()` in `_lib.php`, whose precedence
   is **`q`, then `w=`/`words=`, then the filter sheet** — and only the last of the three
   ever calls `build_word_filter()`.

   **A typed query searches the whole table.** Someone typing a word is asking whether the
   project knows it, not asking to search inside the slice they happen to have open — and
   the defaults leave 2,682 of 18,270 words standing, so a first-time visitor searching
   `celșag` got „niciun rezultat" about a word that is in the database with a definition.
   „Not here" about something that *is* here is the worst answer this site can give, and
   no control on the page was set by that reader or named as the cause. Measured on the
   `-țiune` band: 29 matches of 406 before, 406 after. This is why `marks` is dropped too
   (it is one more row in the same sheet), and why `word_tier` is not re-added here — a
   no-op today, but a filter, and it would silently re-narrow the search the day a second
   tier lands. Sort stays live in both modes: ordering cannot make a match disappear.

   **A playlist** is a list someone curated by hand, and the defaults would quietly
   subtract from it: a shared list of twenty words arriving as eleven, with nothing on the
   page to explain the gap. Searching *within* an open list is what the ordering above
   gives up — deliberately, since a `q` that means "everything" on one page and "these
   twenty" on another is a search box that cannot be trusted to answer the question.

   **A single shared word (`?word=`) is not a third scope.** It goes through the filter
   sheet like any other view — but a share must land on its word, so the controls hiding
   that one word are relaxed and the row is pinned to the top. See **A share lands on the
   word** under the share-metadata section; the difference from these two is that nothing
   is overridden, so every control stays live and says what it is doing.

   The UI half is `setSearchMode()` / `setPlaylistMode()` in `app.js`, marking the form
   `data-search` / `data-playlist`. Both funnel through `applyScopeInert()`, which reads
   the two attributes together — neither may clear `inert` alone, or typing into the box
   with a list open leaves a live-looking sheet the server is not reading. `inert`, not
   `disabled`, so the values survive and leaving either mode hands back the same view.
   The sheet shows one note (search wins where both hold) and the chip bar empties, because
   a control that is not being applied must not keep claiming it is. `resetează` stays
   visible during a search and only hides for a playlist — it clears the query box along
   with everything else, so it *is* the way out the note names. Pinned by
   `tests/test_search_scope.js`.

### `modern_band` — how much life the word still has

`0` absent · `1` faint · `2` still in circulation. The `urme azi` control, and the
replacement for the deleted `rare_in_use` tab.

**Read the direction carefully: more modern usage is *better* material here.** The words
in band 2 are what the project is for — `zapciu`, `birjă`, `vechil`, `dorobanț`, `cocoană`,
`jupâneasă`, `ișlic`. Band 0 is dictionary ghosts that never really circulated — `celșag`,
`racaleț`, `oglavă`, `toroști`, `barabor`. This is the same trap `$SORT_OPTIONS` already
records for `sort=rare` ("put the most obscure regionalisms first — jbârc, barabor,
hâșăi — which is the opposite of what the list is for"). Pinned by
`test_modern_band_points_the_right_way`.

**A band, not a count, and the indirection is the point.** An occurrence count only means
something relative to how much modern text was read, so `mark_modern_band()`
(`tools/build_ui_db.py`) derives the edges from `validate_diachronic`'s own
`MODERN_RARE_OCC` / `MODERN_ALIVE_OCC` through `scaled_modern_thresholds()`, at build time.
A number in PHP would silently change meaning the first time a corpus is added — the drift
the `scaled_modern_thresholds` gotcha below already describes.

Three bands, not four: `alive_occ` is also `make_shortlist`'s eligibility ceiling, so
nothing above it is in the table (max `modern_occ` is 1,998 against a floor of 2,000) and a
fourth option would be a control with nothing behind it.

### `newest_dict_year` — last attestation

The newest dictionary that still prints a word, from `Source.year` via `dict_sources.db`.
97% coverage (17,806 of 18,270). Exposed as `sort=attested`, the `attested_before=<year>` /
`attested_after=<year>` filters (a band when both are set — `attested_after` is `>=`,
`attested_before` is `<`, so they never overlap at the shared boundary year), and the lead
chip in the detail panel's dictionary row.

**Both filters are `curiosity`-seam instruments.** The `relevant` seam requires
`in_current_dict` (2005+) to qualify, so `attested_after` is close to always true there and
`attested_before` close to always false — neither says much there by construction. On
`curiosity` both are sharp: 288 words were last printed before 1970, and that slice is
almost entirely pre-1953-reform orthography (`desbatere`, `sburătoare`, `răsvrătit`,
`vuet`); the ~13.8k at 2005+ are `attested_after`'s more ordinary end of the range.

Rows with no year are excluded when a ceiling is set, and sort last. "Unknown" means the
dictionary is unnamed or unmatched — it is not evidence that a word is old.

## Synonyms

`words.synonyms` / `words.antonyms` come from `scrape_synonyms.py`. **The reason is
narrower than it used to be stated here, and the overstatement cost a year — twice, now.**
What's redacted is `Definition.internalRep`, and the previous fix to this paragraph still
got the scope wrong: it isn't "the three Litera titles" against "the Academy dictionaries"
as a class. Measured across all ~100 `Source` rows while fixing `extract_definitions.py`
(2026-08-17, see `docs/DEFINITIONS_ANALYSIS.md`): only sourceId 1 (DEX '98) and 2 (DEX '96)
ship untruncated text. Every other source is capped at ~23 characters — including *other*
Academy-published dictionaries (DEX '84, DEX '75, DEX-S all say "Academia Română" in their
own `Source.author`), not only the copyright-driven Litera titles:

```
sourceId 1 (DEX '98)    66,185 rows   mean 192.0   max 15,873
sourceId 2 (DEX '96)     4,898 rows   mean 178.4   max  6,785
sourceId 3 (DEX '84)       114 rows   mean  21.1   max     23
sourceId 6 (Sinonime)   49,269 rows   mean  23.0   max     23   "@AB'A@ s. dimie, păn..."
— every other sourceId (~95 of them): mean 17–23, max ≤23
```

So `dict_count` knows a word appears in any of ~100 dictionaries, but DEX '98 and DEX '96
are the only two whose text is actually usable from the dump — everything else, Litera or
Academy, is a stub. `extract_definitions.py`'s `_extract_dex9896_topup()` reads exactly
those two ids for this reason. The rendered page has the rest.

**That says nothing about the `Relation` table, which is a different artefact and ships in
full.** It is dexonline's own community-curated relation graph — 158,860 rows, 152,023 of
them synonym, plus antonym/diminutive/augmentative — and resolving it through
`Meaning → Tree → TreeEntry → EntryLexeme → Lexeme` yields 164,399 word-level synonym
pairs over 63,049 words in ~15 seconds with no HTTP. Nothing in this repo read it until
2026-08-14. The two sources are complementary rather than redundant: measured on the 1,542
words both cover, **59% of the scrape's tokens are new information**, and `Relation` is
strong on modern vocabulary exactly where Seche is weak, and vice versa.

Full measurements, schema and build spec: `docs/sinonime/`.

```bash
python scrape_synonyms.py --dry-run --seam relevant     # count + ETA, no requests
python scrape_synonyms.py --seam relevant --merge       # the default-view words
python scrape_synonyms.py --merge-only                  # re-merge an existing checkpoint
python tools/build_ui_db.py                             # fold into ui.db
```

Resume is automatic and Ctrl+C is safe — each row is flushed as it arrives. `--delay`
below 1.2s is refused outright: dexonline.ro is community-run.

**One scrape at a time, enforced.** `--delay` is a per-process guard, so two copies each
waiting 3s hit the site every 1.5s — which happened on 2026-08-08. `acquire_host_lock()`
takes an exclusive `flock` on `data/.dexonline.lock` before any request; a second run
exits 1 and names the holder. Three properties worth keeping:

- **It is keyed on the host, not the script.** `scrape_definitions.py` talks to the same
  site, and adopting the same two lines makes it interlock with this one. A per-script
  lock would permit exactly the doubling this prevents.
- **`flock`, not a PID file.** The kernel drops it when the process dies, so a `kill -9`
  cannot strand a lock that someone has to `rm` by hand. The pid written inside is only
  read back to name the holder in the error message.
- **`--dry-run` never takes it.** Inspecting the queue while a scrape runs is legitimate;
  it makes no requests.

Two things the parser has to get right, both learned from real output:

1. **A page renders every entry dexonline considers related, not just the one asked
   for.** `/definitie/roză` also carries `ROZ` (the colour). Entries are matched on
   headword — without it `roză` picks up *trandafiriu, rozatic, pembe*. When nothing
   matches, all entries are used, because archaic spellings are the point here and
   dexonline normalises them (`/definitie/poronci` returns only `PORUNCĂ`/`PORUNCI`).
2. **Each entry opens with its own capitalised headword**, sometimes mid-token because
   the markup does not fence it off (`"ROZĂ     trandafir, rug"`). Leading capital runs
   are stripped and still-uppercase tokens dropped: synonyms are lowercase, headwords
   are not. Antonime entries are the exception — ordinary case, `Curajos ≠ fricos, laș` —
   so their headword is read from before the `≠`.

## Gotchas

- **Never compare the two corpora in ppm.** They differ 1,187× in size, so a shared
  `0.1 ppm` floor meant "< 1,697 occurrences" on the modern side and "≥ 1.43" on the
  historical one. That single line classified `zapciu` (1,322 modern hits) as extinct and
  put `vapor`, `fluviu` and `cioban` in "declining".
- **Corpus counts are per surface form.** Always roll them up through
  `inflected_forms.db` before judging a lemma, or every verb reads as extinct.
- **CoRoLa is loaded and deliberately not in any panel — because it spans 1945+, not
  because of its lemmas.** `process_corola.py` loads the **surface-form** lists (1,813,746
  forms, 637.8M tokens) into `corpus_word_frequency`, so DEX's own paradigms do the rollup.
  That solved the lemmatization problem completely: TTL's lists put 12,176 on `strugur` and
  724 on `strugure`, and our `aggregate_by_family` puts it back — 749 and 12,034. Never load
  its `corola_lemma_freq_*` lists; the fix was the input file, not a reconciliation
  algorithm.
  What blocks it is the **time span**. CoRoLa covers 1945 to the present, so presence in it
  is not evidence of *current* use. Against CulturaX per token: `condițiune` 112.8×,
  `comisiune` 49.6×, `dorobanț` 41.1×, `iscăli` 15.7× — the first two are pre-1953-reform
  spellings, which a 1945-onward corpus necessarily contains. Wired into `modern_occ` for
  one build, it removed 35 words from the **relevant** seam, `birjă`, `dorobanț`, `vechil`,
  `dijmă` and `cocoană` among them: the project's best material, gone from the default view.
  The frequency lists carry no dates, so no post-2000 slice can be taken. Using CoRoLa needs
  a third panel with its own meaning ("attested in the reference corpus"), not a term added
  to the modern one. Pinned by `test_corola_is_not_in_the_modern_panel`.
- **Modern occurrence thresholds scale with the panel** (`scaled_modern_thresholds`).
  `MODERN_RARE_OCC`/`MODERN_ALIVE_OCC` were sampled against CulturaX at
  `CALIBRATION_MODERN_TOKENS`; an absolute count only means something relative to how much
  modern text was read, so adding a corpus without rescaling makes every word look more
  alive and pushes everything within the growth margin over a threshold. Any test pinned to
  the bare constants breaks the moment a corpus is added — derive the floor the way
  `tests/test_rescore._rare_floor()` does.
- **`subtitle_ro` is not a modern-usage signal — ~1/6th of it is folk-music television.**
  `process_subtitles.py` calls it "Digi24 news content"; the news is real but so is a large
  body of folklore programming, and the archaic vocabulary in it comes from *sung traditional
  lyrics*. Measured: clips carrying ≥3 genre markers are 15.6% of tokens but 27.5% of all
  shortlist-word occurrences, and **444 of the 2,446 shortlist words it attests appear only in
  those clips**. Scoring subtitle presence as "alive today" would rescue precisely the words
  the project exists to find. Nothing reads `subtitle_ppm` today; keep it that way until the
  folk clips are filtered out (`clipId` is the document unit, so this is doable) or the signal
  is inverted into a traditional-song flag. See `docs/corpus-expansion-plan.md`.
- **In `aggregate_by_family`, documents are share-scaled like occurrences, and taken as a
  max rather than a sum.** Both halves matter. Summing double-counts a document holding two
  forms of the same lemma; crediting documents all-or-nothing (the old `share >= 0.5` rule)
  gave a lemma that never majority-claims any of its forms zero documents while it still
  accumulated occurrences — and since `verdict()` reads `hist_occ >= 3 AND hist_docs >= 2`,
  the docs half silently vetoed the occ half. `văz` sat at 96 occurrences / 0 documents and
  came out `absent` in the relevant seam; 170 shortlist rows were in that state.
- **`dex_pos` comes from `Lexeme.modelType`, not from taxonomy tags.** The meaning-level
  tags cover ~3% of the list and bleed across variants — `visternic` (modelType `M`) came
  out "substantiv feminin" because the entry also covers `vistiernică`. `modelType` is on
  all 317,721 lexemes and gives 99.5% coverage. `T` and `IL` are inflected forms rather
  than headwords and `I` means invariable, so those fall back to `description`.
- **Derive `dex_pos` before building `vocab`**, or the POS dropdown lists values that
  almost nothing matches.
- **Frequency bins disagree** across scripts (0.30/0.50/0.60 in `constants.py` vs
  0.30/0.50/1.01 in `validate_diachronic.py`). `constants.py` is canonical.
- **The sampled dump comments out whole tables** (`-- SAMPLED: INSERT INTO \`Source\``),
  so `extract_dict_sources.py` against it yields no names or years. It warns; heed it.
- **`explore_dex.py` is not a working script** — narrative documentation that can't run.
- **`archive/` is reference only** — the legacy Wikipedia/OSCAR branch, `search_wild.py`
  and the old Flask UI live there. Don't run or import them; see `archive/README.md`.

## Conventions

- **One script per pipeline stage.** No package layout until 3+ modules share helpers.
  `dump_parser.py` is the one shared helper — three extractors use its quote-aware scanner.
- **Romanian normalization:** lowercase → cedilla-to-comma diacritics (`ş→ș`, `ţ→ț`) → `unicodedata.normalize('NFC', …)`. Canonical implementation: `dump_parser.normalize`.
- **Generated artifacts go under `data/`** (gitignored). Never commit `*.db`, `*.csv`, or `data/` contents — except `data/word_ids.tsv` and `data/editorial.tsv`, both tracked on purpose (durable share ids; curator marks).
- **`frequency = 0` means no data, not "rarest".** Filter with `frequency > 0` or `> 0.01`.

## Visual skins

The UI has two independent axes on `<html>`: `data-theme` (light/dark) and `data-skin`.
A skin is a plain CSS file in `public/assets/skins/` — drop one in and it appears in the
dropdown on the next request. There is no registry, no build step, and no PHP to edit.

```
public/assets/skins/
  _template.css   # copy this; underscore-prefixed files are skipped by the scanner
  brutal.css      # "Beton"  — the full brutalist skin, ~1080 lines
  govuk.css       # "Guvern" — GOV.UK Design System homage, ~330 lines
  registru.css    # "Registru" — patronview.com homage, mono headwords, ~620 lines
  tezaur.css      # "Tezaur" — thesaurus.com homage, tinted word pills, ~210 lines
  velin.css       # "Velin"  — worked example, tokens only, ~70 lines
```

Discovery lives in `public/api/_skins.php` (required from `_lib.php`, so all four pages
get it). Three rules:

1. **The filename is the id.** `sepia.css` → every rule scoped under `[data-skin="sepia"]`.
   Ids must match `^[a-z0-9][a-z0-9_-]*$`; anything else is ignored rather than
   half-working.
2. **Scope everything.** All skin files load on every page — the attribute decides which
   applies. An unscoped rule leaks into every skin, including `paper`.
3. **Name it** with an `@skin <label>` tag in a comment near the top, or the filename is
   used as the label.

`paper` is the built-in null skin: `app.css` with nothing on top. It has no file.
`DEFAULT_SKIN` in `_skins.php` sets what a first-time visitor gets.

### What "token" means here

A **token** is one of the ~40 CSS custom properties declared on `:root` at the top of
`app.css`. They are the skinnable surface. `app.css` never hardcodes a colour, font or
radius in a component rule — it says `background: var(--surface)`, never `background:
#F4EFE5`. So redeclaring `--surface` inside `[data-skin="x"]` repaints every rail, card
and sunken area across all four pages without the skin ever naming `.filter-sheet`.

They are named for the **role**, not the value — `--surface`, not `--warm-grey`. That is
the whole trick: a token can take any value in any skin because nothing downstream
assumes what it looks like.

The four groups:

| group | tokens | notes |
|---|---|---|
| surfaces / text | `--bg --surface --surface-2 --border --border-2 --text --text-2 --text-3 --text-4` | `--text-4` is real 9px text (the hist_occ superscript), so it needs 4.5:1 — not a throwaway |
| accent / status | `--accent --accent-bg --on-accent --badge-bg --star --success* --error*` | `--on-accent` must flip to ink in dark blocks, where accents are light |
| verdicts | `--v-{ext,dec,hist,abs}` × `{"" ,-bg,-bd,-tx}`, plus optional `-word` | `-word` only if the skin colours the headword instead of the dot |
| type / metrics | `--sans --serif --mono --radius --bar-h --chip-h --statusbar-h` | `govuk` points all three fonts at one Arial stack and sets `--radius: 0` |

The contrast is a **component rule** — `[data-skin="brutal"] .word-row { … }`. Those
target one element on one page and break if the markup moves. Tokens are cheap and
durable; component rules are neither. This is why `velin.css` is 68 lines and
`brutal.css` is over a thousand: same site, opposite ends of that trade.

Colours that differ between light and dark must be tokens declared in **both** blocks;
hardcoding one is the most common way a skin ends up unreadable at night.

### The Filtre rail is type only — no skin gets a fill there

`.fs-pill` and `.fs-label` carry **no background and no border**, in any state, in any
skin. Checked is said with colour, weight, and at most an underline; the tick and the
verdict swatch inside the pill already state on/off on their own.

This is not a stylistic preference, which is why it is a rule rather than a note in one
skin: **most of these pills are checked when you arrive.** A fill on a checked pill is
therefore not a highlight, it is the background of the rail — ~25 filled rectangles
stacked in a 280px column, louder than the words the rail exists to filter. app.css took
the fill off `.fs-pill` for exactly this reason (the comment is at its declaration), and
every skin then put one back independently: `brutal` inverted both the pills and the
labels to ink blocks, `tezaur` filled them with the accent, `govuk` with `--surface`, and
`registru` made the labels into §-tags. All four are fixed; the trap is that each one
looks reasonable while you are writing that skin alone.

`.seg-opt` is the exception and is **not** covered by this. It is a segmented control with
no tick and no swatch, so the inverted block is the only thing saying which option is
live — and it is app.css's own treatment, identical under every skin.

### `.dex-link` is a chip in the dictionary row, not a button

The dexonline link sits at the end of `.fp-dicts`, shaped off `.dict-chip` — one more
dictionary reference among the names, which is what it is. It used to be a full-width
filled block at the foot of the panel, and **every skin independently made it louder**:
beton a red accent slab with a drop shadow, govuk the green GDS action button, registru a
black rectangle in mono caps, tezaur a filled pill. The result was that the loudest element
in the detail panel — ahead of the headword and the definition — was a link off the site.

That is the same trap as the Filtre rail above, and it has the same cause: each skin looked
reasonable while you were writing it alone. A big filled button invites being styled like a
primary action, so the fix is the shape, not four more overrides. All four skins now add at
most a colour to it (`registru` re-grounds because `--accent` there is the page's own ink,
which says nothing on a chip among chips).

**`.fp-dicts` renders even when a word has no `sources`**, because the link lives in it now;
wrapping the row in `if ($sources)` would drop the link for exactly the words whose
dictionary coverage is thinnest. Verified at 4.5:1 or better in all five skins × both themes.

### A skin must never be able to flatten a *state* — hence `.fp-btns` on the marked rules

The quick-tag buttons (`fav` / `lol` / `meh` in the detail panel) are **toggles**: pressing
an applied tag removes it. So the applied state is the affordance, not decoration — without
it the panel invites you to press `lol` on a word that is already `lol`, and the click
un-tags it.

`app.css` styles that state as `.fp-btns .qt-btn.active` / `.fp-btns #bookmark-btn.active`,
and the `.fp-btns` is there **purely for specificity**. As bare `.qt-btn.active` the rule is
(0,2,0) — exactly the weight of a skin's own `[data-skin="x"] .qt-btn`, which loads after
`app.css` and therefore won. A skin restyling the button's *resting* background silently
repainted the pressed one to match, with no rule anywhere naming `.active`. Measured
2026-08-12: `brutal` and `registru` had both flattened fav/lol/meh to a single appearance,
and brutal's own comment claimed "the pressed one is filled solid" while its only `.active`
rule set a border colour the base rule two blocks above had already set. `#bookmark-btn` has
the same problem for the same reason — an id plus an attribute selector is only (1,1,0),
which `[data-skin="x"] #bookmark-btn` matches exactly.

At (0,3,0) a skin's base rule can no longer reach the pressed state, and because everything
in those rules is token-driven, **a new skin gets a visible marked state in its own palette
for free**. A skin that wants its own treatment overrides `.fp-btns .qt-btn.active`
deliberately, which is the point. `brutal` and `registru` now do (both invert to a solid
block, matching what each already says with `.seg-opt`).

This is the third instance of one pattern, after the Filtre rail and `.dex-link` above, and
the generalisation is worth stating: **a token gives a skin a colour to change; a state
needs a rule a skin cannot outrank by accident.** When you add a component with an on/off
appearance, put the "on" rule out of reach of `[data-skin] .thing` and check it in all five
skins — the failure is invisible while you are writing any one skin.

`.active` is also mirrored into `aria-pressed` by `hydrateDetail()` (`store.js`), with
`aria-pressed="false"` in `detail.php`'s markup so the buttons do not announce as plain
buttons for the tick before hydration. A state said only in colour is no state at all to a
screen reader, or to anyone who cannot separate the two hues a given skin picked.

`govuk.css` was built partly to find where the contract runs out. It did: the black
masthead, the yellow focus state, square marks, dotless tags, the green button and the
inset rule all needed component rules. That list, and the two hooks worth adding if a
third skin wants them, is in `docs/BACKLOG.md`.

`registru.css` is the first skin to repoint `--serif` at a monospace, and that turned up
two things worth knowing before the next one does it:

- **`--word-col` moves with the display font.** It was measured against Source Serif 4;
  Plex Mono is ~25% wider per character, and leaving the token alone puts ordinary
  headwords into the ellipsis. Treat it as part of the type decision, not a layout one.
- **A skin whose `--accent` is the page's own ink has to re-ground anything that fills
  with it inside a dark masthead.** `.joc-mode.active` paints itself `--accent`, which
  under this skin is black — on a black bar the selected game mode simply disappeared.
  `govuk` re-grounds the bar's controls for the same reason, so the list of what lives up
  there is worth copying wholesale rather than rediscovering.

Skin files load with an mtime query string, so edits show on plain reload. A stored skin
whose file has since been deleted falls back to `DEFAULT_SKIN` (the valid list is baked
into the pre-paint boot script).

## `--statusbar-h` is measured, not declared

On mobile the footer is `position: fixed`, so that token is a **reservation**: `body`'s
bottom padding, the detail sheet's `bottom` and the toast's all read it. Too small and the
last row of the list sits under the bar; too large and there is a band of blank page above
it.

**It cannot be right as a constant**, and the reason is the point: the bar's height is a
function of viewport width **and** text scale **and** skin, and it changes by *reflow*
rather than by scale — one line at 540px/100%, two at 540px/125%. Measured over 6 skins ×
5 widths × 3 text scales, no set of CSS values covers all 90; the best static attempt
still under-reserved 16.

So `prefs.js` reads the rendered height off `#status-bar` and writes the token back
(`ResizeObserver`, ~10 lines, at the bottom of the file). Every skin, width, text scale
and anything added to the bar later is handled without a breakpoint. Measured
over-reservation across the matrix is now ≤1px, against 49px and 56px before.

Three things to keep:

1. **Nothing that sizes the bar may read the token.** `#status-bar` had
   `height: var(--statusbar-h)`; measuring it back would close a feedback loop and the
   observer would oscillate. The bar sizes to its content — that is why the hard height
   is gone, and it fixed a second bug on the way: a fixed bar that outgrew its `height`
   clipped a control silently.
2. **The CSS values stay, as the pre-JS fallback.** They are what the first frame and a
   scriptless page (`despre.html`) get, so they should stay roughly right rather than rot.
   `1.75rem` below 768px, `3rem` below 480px — `rem` so they track the A−/A+ stepper.
3. **No per-skin override.** `brutal`'s bar is genuinely taller (heavier type, 7px of its
   own padding), and a static `--statusbar-h` for it was written and then removed: a
   per-skin constant cannot track the reflow either. Measuring covers it.

The history is worth knowing because it repeats: `44px`, then `76px` at ≤710, then `96px`
at ≤480 — each an honest measurement when written, each outliving the wrap it was written
for, and the ≤480 one still hard-clipping. Pinned by `tests/test_footer_metrics.js`.

## The definition panel — a centred card, at every width

`#detail-panel` was a 380px right-hand column on desktop and a bottom sheet on the phone.
Since 2026-08-12 it is the sheet everywhere, capped and centred rather than full-bleed. The
column put the definition at the far edge of a wide screen while the word you clicked
stayed on the left; capping the width keeps the line length in the 45–75 characters prose
wants, instead of the ~200 a 1800px pane gives.

Four things to keep:

1. **It is centred on the list, not on the window.** The filter rail is a docked 288px
   column from 1024px up, so viewport-centring slides the card left by a rail's width and
   tucks its first ~50px — the headword — underneath. Both the offset and the width
   subtract `--rail-w`, which is `0px` by default and `288px` in the block that docks the
   rail, so one expression covers both. **`--rail-w` must stay equal to the rail's
   `flex-basis`**; they are two numbers that have to agree, which is why the rail's block
   sets the token right next to its own width.
2. **`scroll-padding-bottom` on `#word-list-container` is load-bearing, not polish.** The
   card overlays the list, so without it the last rows sit under it permanently *and*
   `scrollIntoView({block:'nearest'})` — what `j`/`k` use — counts them as already visible.
   One property covers both, and the keyboard handler needs to know nothing about it.
3. **`--panel-shadow` is a token declared in both theme blocks.** A shadow tuned for paper
   is invisible over `#1A1613` and the card loses its edge. This is the "define it in both
   blocks" rule from the skins section, on the one component that now floats.
4. **Two skins had rules written for the column and both were wrong as a card** — `brutal`
   gave it a `border-left` as its only edge (three sides open, reads as a torn strip),
   `registru` killed the shadow outright (leaving only app.css's 1px border). Both fixed.
   A skin restyling this panel should give it an edge *and* a lift in its own idiom; a
   floating card with neither disappears into the list. The failure is invisible while you
   are writing any one skin — screenshot all six.

The phone keeps its own treatment below 768px: full bleed, both bars hidden
(`body.detail-open`), 60vh. See the header/footer section for why the bars go.

## App shells vs documents — `body.page-doc`

`app.css` styles `body` as the **explorer's** shell: `height: 100vh; overflow: hidden`, a
flex column whose `#word-list-container` scrolls inside itself. Every page that loads
app.css inherits that, and for a page that is simply prose it means **the page cannot be
scrolled at all**.

`liste.php`, `lista.php` and `despre.html` therefore set `class="page-doc"` on `<body>`,
which restores `height: auto; min-height: 100vh; overflow: visible`. `index.php`,
`ghici.php` and `stats.php` are real shells and keep the default (`stats.php` says so with
its own inline style).

**This hid for months because it only broke on desktop.** The `max-width: 768px` block
already relaxes `body { overflow: visible }`, so narrowing the window made the page scroll
and made the bug look like a rendering quirk rather than a missing class. If a new page is
mostly text, it needs `page-doc`; check it at a *wide* viewport, because the mobile one
will lie to you.

## Document pages — `assets/doc.css` + `assets/doc.js`

`despre.html` and `metodologie.html` share a sticky table of contents and a side-figure
layout. They have separate stylesheets and separate token blocks, but the token *names*
match (`--text`, `--accent`, `--sans`, `--mono`), so one file styles both without either
owning it.

The layout is a two-column grid — **sticky TOC · content** — above 1080px, collapsing to
one column below. Figures stay *inside* the content column: **portrait ones float right at
36%** so the prose wraps beside them, landscape ones stay in the flow at full width. The
rule is orientation, not size, and it is worth keeping that way — a landscape screenshot
squeezed to a quarter width is unreadable, and it leaves the text in a gutter of its own.
`float` rather than a grid cell because text has to wrap back under a short figure and a
figure has to sit next to *its* paragraph rather than at whatever row boundary the grid
picks.

Three things to know before touching it:

- **`doc.js` has two modes.** `metodologie.html` ships a hand-written `<ol>` whose wording
  is editorial (it shortens „Faza 2 — Validare diacronică" to „Faza 2"), so that list is
  left alone and only gets scroll-spy. `despre.html` has no list, so one is built from its
  headings. The contract is the same either way: a container with
  `data-toc="<selector for the content>"`.
- **Scroll-spy tracks the last heading *past* the reading line, not the intersecting
  one.** Sections here run from two paragraphs to forty; "is visible" marks several at
  once and flickers on every scroll tick.
- **A page adopting this must raise its `max-width`.** `metodologie.html` capped `.article`
  at 760px for a single column; as a grid that cap squeezes every track, and the page went
  from 13.5k to **30k** pixels tall before it was raised — taller on desktop than on
  mobile, which is the tell. Both pages sit at 1110px (200 TOC + 44 gap + 820 text).

## Page shell — header and footer partials

All six pages (`index`, `stats`, `ghici`, `lista`, `liste`, `colectii`) draw the same two
partials.
Before them, each page rolled its own bar and `stats.php` had no brand at all.

```php
<?php $page = 'stats'; $brand_tag = 'statistici'; require __DIR__ . '/api/_partials/header.php'; ?>
...
<?php require __DIR__ . '/api/_partials/footer.php'; ?>
```

**Identity plus travel at the top as far as the width allows; the overflow and the display
preferences at the bottom.** `header.php` is brand, a top nav, and whatever is genuinely
page-specific (search, count, play, filters). `footer.php` is GitHub plus the
text-scale/skin/theme toggles, since those are the same on every page — **it draws no nav
entries at all any more**, see below. `cuvinte` (index)
appears in neither — the brand mark already links home on every page, so a nav entry to the
same place was pure redundancy. The split exists at all because the explorer's top bar was
already carrying brand, search, count, play and filters, and a full five-entry nav plus
three toggles is what broke it; `index.php` had already put its counts and legend in the
bottom bar, which is also thumb-reachable on a phone.

**`despre` is the nav's third entry, and it replaced `statistici` + `metodologie`
rather than joining them.** Three labelled entries competing for a phone bar is the
measurement this header/footer split was built on; a fourth broke it again. Both pages are
linked from `despre` instead — and a reader who wants the method has nearly always read the
overview first. They stay in `NAV_ITEMS` so `$page` still marks them `aria-current`; the
two partials name the keys they draw rather than diffing the const, or a diff would put
them silently back.

**`liste` is in `NAV_ITEMS` and in neither bar for the same reason** (2026-08-13): the
second slot now points at `/colectii`, the site-wide aggregate, and `/liste` is linked
from the top of it. That was a swap, not an addition — see the Lists section for why the
aggregate is the one a first-time visitor can read.

**`despre` is in the header at every width — a labelled entry above 901px, the `?` chip
below it. It is no longer in the footer at all** (2026-08-13). `ghici` and `colectii` stay
in the header at every width; they are the two places people jump to mid-browse.

It used to be drawn by *both* partials with app.css picking one — header above 901px,
footer below. **The footer half did not work.** Mobile readers did not press an ℹ️ parked
at the end of a row of display toggles, so the page that explains what the marks mean went
unread by exactly the readers with no other route to it — and „ce înseamnă *fav* / *lol* /
*meh*" is a question only `despre` answers.

The obvious fix is to promote it into the top nav at every width, and **it does not fit**:
the top nav keeps its labels below 901px, so DESPRE with its icon and gap is ~69px of a
390px bar that also carries the wordmark, a search toggle and the filter button. So it goes
in as a glyph instead, in the slot `index.php`'s shortcuts `?` vacates at the same
breakpoint:

- **`.shortcuts-link--wide` / `--narrow` are one slot, one at a time.** The wide half is
  the explorer's shortcuts/legend modal (index-only); the narrow half is header.php's link
  to `despre`, drawn on every page. Same cap, same width, so the bar does not move at the
  crossover on the page that has both. Measured over 4 pages × 6 skins × 9 widths: no
  horizontal overflow anywhere, exactly one route to `despre` at every combination, never
  two.
- **The `?` is worth spending on `despre` because the modal is mostly keyboard
  shortcuts** — unreachable on a phone — and the third of it that is the colour legend is
  in `despre.html` verbatim. Nothing is lost below 901px; the marks are explained for the
  first time.
- **The chip is a 40×40 target with a 19×17 cap.** `min-width`/`min-height` plus `margin:
  0 -4px`, so the box grows for the thumb and gives 8px back to the bar — the same trick
  `.fp-close` uses, and the reason the 320px measurement still has no overflow. The `-4px`
  bleed stops 1px short of `.brand-right`'s 6px gap, so it cannot swallow the search
  toggle's clicks (pinned by measurement, not by eye).
- **`ghici` hides the chip below 768px**, in its own style block beside the other things
  that bar drops. It is ~26px with its gap, a third of the 70px deficit that block exists
  to close. Nothing regresses: ghici hides the footer at that width too, so `despre` never
  had a route from a phone-sized round — and between 769 and 900px the chip is there.

That is about the `despre` *entry*, drawn on the pages that use the partials. **The despre
page itself no longer draws either one** — it is static `despre.html` since 2026-08-12, with
the header nav inlined as a copy and no footer at all. `NAV_ITEMS` is still the source of
truth everywhere else; the copy in that one file is hand-maintained, and its own header
comment says so.

901px is reused deliberately: it was already the footer nav's label/icon breakpoint, so
there is one crossover in `app.css` to keep in step rather than two that can drift. Both
`--wide`/`--narrow` pairs sit on it.
**`.top-nav-item--wide` must stay declared *after* `.top-nav-item`** — both are one class,
so the cascade falls to source order, and above it the `display: none` silently loses and
every entry renders on a phone.

**`$page` marks the current entry in the top nav**, so set it *before* requiring
`header.php`. `footer.php` still accepts it and no longer uses it — it has no nav entries
left to mark. `lista.php` deliberately leaves it unset: it is not `liste.php`, so nothing
in the nav should render as current and stop being clickable.

`header.php` takes five optional slots, all raw HTML strings, so a caller can build one with
`ob_start()` and keep writing ordinary markup: `$header_nav_extra` (in the right cluster,
after the `despre` chip — the explorer's `?` shortcuts/legend link, index-only and
wide-only), `$header_center`
(the explorer's collapsible search — a magnifier `.search-toggle-btn` that reveals `#search`
inside `.search-wrap`, see `openSearch()`/`closeSearchIfEmpty()` in `app.js`), `$header_tools`
(spinner + result count), `$header_after` (the filter button, which has
to stay last). `footer.php` takes `$footer_left` (the explorer's counts), `$footer_extra` (the
colour legend) and `$footer_tools` (the explorer's cloud/table view toggle — index-only,
everything else in the footer is universal) plus `$page`. The explorer's feed button
(`enterFeed()`) is currently `hidden` in the markup rather than wired to either bar — like
the dormant 🎲 `surpriseWord()` button beside it, it has no home yet, not no code.

Five things to preserve:

1. **`NAV_ITEMS` lives in `_lib.php`**, not in either partial — a `const` in an included
   file cannot be guarded against a second include, and it sits with `VERDICTS`/`TIERS`
   as the other list of user-facing strings drawn on every page. `header.php` loops the
   three keys it draws (`ghici`, `colectii`, `despre`) with their width class and reads
   `despre`'s path from it for the chip too; `footer.php` draws none. Both read path/icon/label from `NAV_ITEMS` rather
   than restating them.
2. **The current page stays an `<a>`** with `aria-current="page"` and an accent underline.
   As a `<span>` it stopped matching every skin's `#status-bar a` rule and needed its own
   colour — and `var(--text)` is a *page*-ground token, which on beton's ink footer meant
   near-black on black. Never give this bar a colour of its own.
3. **A nav entry keeps at least one of its icon and its label, and which one is a
   per-bar decision.** Below 768px the top nav is **labels only** — the two emoji buy
   ~34px on a 320px bar and say nothing the words beside them do not. `ghici.php` does the
   exact reverse for its own bar (icons only; its bar also carries a mode switch, a score
   and a trophy), so **it re-declares `display` on `.top-nav .nav-icon`** — without that
   the two rules meet and its nav renders empty. Touching either one means checking the
   other. A bare glyph row beside the wordmark is still what the top bar avoids everywhere
   else, and it is the constraint the `?` chip exists to route around.
   **If a nav entry ever returns to the footer, its label-hiding rule must be scoped
   `.site-nav .nav-label`** — the class is the same in both bars, and the unscoped version
   once turned the header into a row of bare emoji. That rule went out of app.css with the
   last footer entry, along with `.nav-item` and `nav-item--wide`; git history has all
   three.
4. **On a phone, an open definition hides both bars.** `app.js` puts `detail-open` on
   `<body>` when the sheet opens and takes it off in `closePanel()`; only the ≤768px block
   acts on it, so a desktop window narrowed with the panel up lands in the right state with
   no resize listener. The backlog asked instead for the sheet capped at 40% — it is still
   60vh, because 40% of a phone does not hold a definition (measured: `poporanism` alone
   overflows it) and the definition is what you opened. The room comes from the bars: ~186px
   of a 812px screen, neither of which you can act on while reading. Visible list goes from
   ~139px to ~325px and the sheet keeps its height. **With the header gone, `.fp-close` is
   the only way out** — hence the second glyph in `detail.php`: a ✕ top-right on desktop, a
   ← in the top-left corner at a 44px target on a phone. Both are in the markup with app.css
   showing one, rather than a CSS `content` swap that assistive tech cannot see.
5. **`govuk` and `registru` force `.brand-bar` black in both themes**, so anything living in
   it needs on-bar re-grounding in those two skin files (`--gv-on-bar`/`--rg-on-bar`) —
   `.top-nav-item`, `.shortcuts-link` and `kbd` all needed it when they moved up from the
   footer, a page-ground surface neither skin forces dark. The reverse also holds: a
   control that moves *out* of `.brand-bar` (scale/skin/theme, feed/view-toggle, all now in
   the footer) should have its now-dead `.brand-bar`-scoped rules removed from both files,
   not left to rot — exactly the risk the skins section above already names for component
   rules in general.

`lista.php` sets `$brand_tag` but deliberately no `$page`: it is not `liste.php`, so
nothing in the nav should render as current and stop being clickable.

### `.brand-bar` takes `min-height`, never `height`

The bar wraps to two and three rows on a narrow phone — `.brand-right` has
`flex-wrap: wrap` below 768px, by design, and at 320px there is no arrangement that does
not. A hard `height` does not grow with that: the extra rows render **outside the painted
box**, on the page ground. On the two skins whose masthead is black that means on-bar
*white* text on a white page — the `?` chip and the filter button, invisible, and invisible
only at the widths nobody develops at.

app.css always had `height: auto` in its mobile block, so this looked handled. **`govuk.css`
had `height: calc(var(--bar-h) + 10px)` at (0,2,0) and loads after app.css**, so it won and
only that skin broke. Both are `min-height` now. This is the same rule `#status-bar` lives
by at the other end of the page and for the same reason — see **`--statusbar-h` is measured,
not declared**, whose point 1 is the identical trap. A skin may raise the bar; it may not
pin it.

**The fix is the bar, not the buttons.** The obvious patch is a background on whatever
lands in row two, and it is wrong twice over: it treats one symptom of a container that
cannot contain its contents, and it needs re-doing in every skin for every control ever
added to that bar. With the bar growing, anything in it sits on the bar's own ground for
free.

Three width reductions landed with it, all in the ≤768px block, and together they take the
bar back to **one row at 360px and up** (measured: 97px → 59px at 390px, every skin):

- **The top nav's icons go** (see point 3 above).
- **The wordmark drops to 1.125rem**, as `.brand-bar .brand-id .brand-name` — three deep
  because brutal (1.5rem) and registru (1.25rem) size it at (0,2,0) and load later. It is a
  width adaptation rather than a style choice, so it overrides them on purpose; a skin can
  still take it back inside its own media query, which is what `brutal.css` already does at
  560px and `ghici.php` now does for its own bar.
- **The filter button loses its border and padding**, at `.brand-bar .brand-right
  .filter-toggle-btn` for the same specificity reason. govuk and registru set `border-color`
  only, so `border: 0` takes their border off without a fight. **Its hit box comes back as
  a box, not as padding** — stripped it measured 16×30, narrower than the bare magnifier
  beside it; it is 30×36 now, matching `.search-toggle-btn`. No negative margin, unlike the
  `?` chip: the two are adjacent in `.brand-right` with a 6px gap, and two bleeds would
  overlap and let the later one steal the other's clicks (hit-tested with
  `elementFromPoint`, not eyeballed).

Measured after, 4 pages × 6 skins × 9 widths from 240px up: nothing renders outside the
bar's painted box, no nav entry renders empty, and every control in the bar receives its own
clicks.

## Lists — „Colecții" (`/colectii`) and „Liste" (`/liste`)

**Two pages, and the nav points at the aggregate one.** Since 2026-08-13:

| URL | title | what it is |
|---|---|---|
| `/colectii` | Colecții | **site-wide**: what every visitor marked, two ranked tabs. In the top nav. |
| `/liste` | Liste | **yours**: the three buckets, publishing, and the public directory. Linked from the top of `/colectii`. |

The table, the endpoints and the slugs are still `lists` / `lista` / `liste` — `/liste` is
a shared-link surface and `lists.source_tag` is stored data, so neither moved. The one
other place the word survives on screen is despre's „Cele două liste", which is about the
*seams* and is a different sense of it.

**Which page owns the nav slot was the whole decision.** The bar takes exactly three
labelled entries (see `header.php`'s docblock for the phone measurement), and `/liste`
held it for a year. But a visitor who has marked nothing — which is every visitor on their
first read — opened „colecții" and got three empty cards plus other people's published
lists: a page about publishing, on a site whose readers mostly browse. The aggregate is
what that reader can actually read, so it took the slot and `/liste` went one click in.
Nothing on `/liste` changed but its title.

### `/colectii` — the site-wide aggregate

Two tabs over `mark_counts_subquery()` (`api/_appdb.php`): **îndrăgite** ranked on `n_up`
(★ or 🤣) and **respinse** on `n_down` (⛔️). Server-rendered, no `current_user()` call
anywhere in the file — a public read must not mint a device identity for every passing
crawler, the guard `lista.php` already documents.

Four things to keep:

- **The ranking counts people, not marks.** The annotations PK is `(user_id, word)`, so
  `n_up` is a distinct-person count and is **not** `n_fav + n_lol` — one person who both
  ★'d and 🤣'd a word counts once, while showing in both breakdown chips. Ranking on the
  sum lets one person's two keystrokes outrank two people.
- **fav-beats-meh is a rule about a *person*, not about a word**, and the two readings
  differ in what they hide. Within one row the ★ wins, as in `vote_counts_subquery()`. But
  `subdialect` is ★'d by 19 people and ⛔️'d by 4 others, so it is on **both** tabs — which
  is a real disagreement and not a bug. The chip therefore names the opposing counts on
  the respinse tab too (`⛔️4 · ★19`); leading with „⛔️4" alone would report a word 19
  people liked as rejected. Pinned by `tests/test_colectii.js` §3 and §5.
- **The counts are raw, with no `VOTE_BOOST_SQL` damping, deliberately.** Damping exists so
  stuffing cannot move a word far in a *mixed* score; here the count is the entire content
  of the row, and any monotone damping leaves the order byte-identical while hiding the
  number. The page still only ever *adds* a surface — it removes nothing from the explorer,
  which is the invariant that makes a page driven by anonymous device tokens safe to
  publish at all.
- **The tab counts go through the same `words` JOIN as the rows.** A word can keep its
  marks in app.db after leaving `ui.db` in a rebuild; counted without the join, the tab
  advertised 70 above a list of 67.

Unlike `/liste` it is **indexable**: every string on it comes from `ui.db` or is an
integer, so the `noindex` protecting the public directory has nothing to do here.

### `/liste` — your buckets and the directory

**The three buckets are the collections.** `fav` / `lol` / `meh` (declared once in
`LIST_BUCKETS`, `api/_appdb.php`) are derived from `app.db.annotations` on every request via
`bucket_words()` — never stored, so they cannot drift out of date. `liste.php` shows them
and a directory of everyone's public ones.

**`ascunde` was retired as a bucket** — it said what `meh` says with a harsher name, and
its button was already commented out of `detail.php`. The tag is *not* forgotten:
`api/quiz.php` reads `tag:ascunde` literally when picking distractors and old annotations
still resolve. It is only no longer publishable. Anything published from it before the
retirement keeps its row and its words, and surfaces under „Alte liste" (below) with
„actualizează" gone — which is what retiring a source means. `index.php`'s shortcut table
still lists the `a` key; that predates this and is a separate decision.

**One card per bucket, published or not** — there is no second „Publicate de mine"
section. It used to list the published rows, so the same collection appeared twice under
two names („favorite" above, „favorite — pax1" below) with its actions split between them:
publish up here, refresh/unpublish/delete down there. A published row is a *state* of the
bucket, not a sibling of it. Three consequences worth keeping:

- **„publică" always means `publish_bucket`**, never `update {is_public:1}` — including
  re-publishing one that was made private. `publish_bucket` reuses the existing row *and*
  refills it, so re-publishing cannot hand out a stale snapshot. `toggle-public` is left
  doing only the one direction that needs no refill (`fă privată`).
- **The card shows the live bucket count**, and names the published count separately when
  the two differ („9 cuvinte în versiunea publicată — apasă *actualizează*"). Showing one
  number for both is how a published list silently goes stale.
- **`șterge` on a bucket card removes the published snapshot, not the marks**, so its
  confirm says so. On the old page the button sat on a row that *was* only the snapshot;
  here it sits on the bucket.

**„Alte liste" is the escape hatch and must not be dropped.** Anything whose `source_tag`
is `''` (hand-assembled through `create` + `add`) or names a retired bucket has no card to
fold into. Rendering only the three buckets would make those unreachable rather than tidy.
The section hides itself when empty, which is the normal case.

**The „Alese" card was removed** from this page (2026-08-12) as duplicating „Colecțiile
mele" for the one reader who is also the curator. `editor_pick` still drives the ★ chip in
the explorer and still comes from `data/editorial.tsv`; it simply has no surface on
`liste.php` any more. If it is ever wanted back, the argument for it was that it needs no
user, no publish step and no app.db state — it reads `ui.db` directly, so it is there on a
fresh install with zero visitors.

A row in the `lists` table is a **published snapshot** of a bucket. `lists.source_tag`
records which one:

- `POST {action:'publish_bucket', bucket}` — create-or-reuse the caller's list for that
  bucket and fill it from their own annotations. One list per bucket per user. The client
  never sends the words.
- `POST {action:'refresh', id}` — re-read the bucket. Words already present keep their
  `position` so a re-sync doesn't reshuffle a list someone has already read.
- `source_tag = ''` means hand-assembled — every list created through `create` + `add`,
  which still work unchanged. Those cannot be refreshed.

This is why there is no per-word "add to list", no grid multi-select and no inline list
editing: you curate by marking words while browsing, and publishing is one button.

**Marking advances to the next word — all four marks, the same way.** `advanceAfterMark()`
in `app.js`, called from both handlers in `store.js`. Three properties, each of which has a
reason someone will otherwise remove:

- **All four, not just the hiding ones.** The first cut advanced only on `meh`/`ascunde`, on
  the argument that `fav` and `lol` are stackable on one word. That was overruled and the
  reasoning is worth keeping: marking is a triage loop, one mark per word is the intended
  interaction, and a loop where three keys move you on and one does not is a loop you have to
  think about. Consistency beats the rare double-tag.
- **Applying advances; removing does not.** Un-favouriting is a correction — advancing would
  take you off the word you just came back to fix.
- **`removesRow` is the only branch.** `meh`/`ascunde` also pop the row out, so the next row
  must be resolved *before* the fade and re-found by element after it: resolving it later
  races the animation, and taking it by index earlier leaves `selectedIdx` off by one the
  moment the row goes — and that is the number `j`/`k` read. On the last row, fall back to
  the previous word when the row is being removed and stay put when it is not; never wrap to
  the top, which silently restarts the list.

Custom tags typed into `#tag-input` deliberately do not advance — it would pull focus out of
the field mid-typing.

### Moderation

The public directory (`GET api/lists.php?public=1`) has a report/takedown path:

- `POST {action:'report', slug, reason?}` — anyone can flag a **public** list that isn't
  theirs. Addressed by slug, because a reporter is a reader. A private or missing list
  both answer `404`, so the endpoint can't be used to probe which slugs exist. One report
  per user per list (`idx_reports_once`); re-reporting is a silent no-op that returns the
  same success, so a reporter learns nothing about whether their first one landed.
- **`public/admin.php`** — the queue, grouped by list, most-reported first. Unpublish
  (`is_public = 0`, reports → `removed`), dismiss (→ `dismissed`), or delete outright.
  Unpublish is the default action and leaves the owner's data intact; delete is the only
  irreversible one.

Access is a shared token in `api/config.local.php`:

```php
define('OTIOS_ADMIN_TOKEN', '<48+ random hex chars>');   // openssl rand -hex 24
```

Two things about that page worth not undoing:

1. **No token defined, or a wrong one, means `404` — not `403`.** An install that never
   configured moderation gives nothing away when probed.
2. **The token is passed once as `?token=`, then sealed into a cookie** (`seal_token()`,
   8h) and the page redirects to the bare URL, so it leaves the address bar, history,
   access log and any Referer. This is also why the page sets `referrer: same-origin`
   rather than `no-referrer` — `no-referrer` serializes `Origin` as `null`, which is
   exactly what `require_post_same_origin()` rejects, and its own forms POST back to it.

**There is deliberately no auto-hide-after-N-reports rule.** Identity here is an anonymous
device token, so "three different users reported this" costs an abuser three cookie
clears — a report threshold would be a cheaper way to censor a list than to publish one.
Reports queue for a human.

`liste.php` is still `noindex`; lifting that is now a product decision rather than a
blocker.

### Backing up `app.db`

`private/app.db` is the only irreplaceable file in a deploy — `ui.db` regenerates from the
pipeline, but annotations, lists, nicknames and the game log exist nowhere else.

```bash
php api/_backup.php              # snapshot + prune, keeping the newest 14
php api/_backup.php --keep 30    # keep more
php api/_backup.php --dir /mnt/x # write somewhere else (an external mount)
php api/_backup.php --list       # show what's there, write nothing
```

Nightly, from the deployed app folder:

```cron
17 3 * * * cd ~/voroave.ro && php api/_backup.php >> ~/voroave-private/backup.log 2>&1
```

It lives in `public/api/` because **only the contents of `public/` are deployed** — a
script anywhere else in the repo is not on the server. It is CLI-only: `PHP_SAPI !== 'cli'`
returns 404 before any include, so it is inert over HTTP. It uses `VACUUM INTO` rather
than `copy()`, because in WAL mode the committed data is split across `app.db` and
`app.db-wal` and a file copy can land mid-transaction; every snapshot is then reopened and
`PRAGMA integrity_check`ed before old ones are pruned.

This does not replace an off-machine backup. A snapshot beside the original survives a bad
migration or a mistaken delete, not a lost disk.

## The quiz — `ghici.php` („Quiz" in the nav, `/ghici`)

Was `joc.php` until 2026-08-12. **Three names, all different on purpose**: the nav label
is `quiz`, the URL is `/ghici`, and the `NAV_ITEMS` key — what `$page` and `aria-current`
match on — is `ghici`. `/joc` and `/joc.php` 301 to it; that is the one redirect in
`.htaccess`, safe only because no API endpoint ever answered there (see the note beside it
for why a blanket redirect rule is not).

**`?game=` is the public spelling; `mode` is the internal one.** `game=sensuri|grila|carduri`
maps to `mode=sense|quiz|flash` in one table at the top of the page script. Everything
below — `api/quiz.php`, `api/game.php`, `api/leaderboard.php`, `localStorage['otios.quiz']`
and the server's per-mode stats — keeps talking in `sense`/`quiz`/`flash`. Renaming those
would re-key stored state, which is the same class of change as renaming the device cookie.
`?mode=` still resolves: it was the only spelling for months, and `?mode=flash` is how the
unlisted card mode is reached. `setMode()` writes the URL with `replaceState`, not
`pushState` — the two modes are views of one activity, and the question itself is never in
the URL, so history entries would restore nothing.

### What counts as a spoiler in `sensuri`

The detail pane is **the explorer's own widget**, so it arrives carrying the answer twice:
`.definition-text` is literally one of the four choices, and `.fp-pos-line` is the one
people miss — „s.f." beside the headword eliminates every option phrased as a verb, which
on a four-option round is most of the work. Both, plus the card's own `.joc-pos`, get
`.joc-spoiler` until the round is decided, then `revealSpoilers()` takes it off.

**`roundDecided` is a separate flag from `answered`, and it is load-bearing.** `answered`
goes true when a choice is clicked; `roundDecided` when the verdict is on screen.
`showWordDetail()` is a fetch, so a fast answer can land while the pane is still in
flight — without the flag the pane resolves *after* the reveal and re-hides the definition
the verdict just uncovered, leaving „✅ corect!" above an empty panel. Pinned by
`tests/test_ghici.js` §3.

### Marks beside a grilă option — why they are not detail.php's

In `grilă` every option *is* a word, so all four are markable before answering — the
fastest triage on the site, four words a question. They deliberately do **not** reuse
`detail.php`'s `#bookmark-btn` / `#tags-row` markup: those are addressed by *id* in
store.js's delegated handler, so four copies on one screen would be four elements sharing
one id with one of them answering for the rest. `.joc-mark[data-joc-word][data-joc-tag]`
instead, handled on `#joc-card` and calling the same `getWord`/`updateWord` store.

**They are siblings of the option button, never children.** `.joc-choice` is a `<button>`,
and a `<button>` inside a `<button>` is invalid markup that parsers recover from by
dropping the inner one — so the failure looks like "the marks vanished", not like an error.
`.joc-choice-row` is the wrapper that keeps them apart. Pinned by `test_ghici.js` §5.

The applied state is styled `.joc-marks .joc-mark.active`, two classes deep, for the reason
the skins section gives at `.fp-btns .qt-btn.active`: a skin's `[data-skin="x"] .joc-mark`
would otherwise repaint the pressed state along with the resting one.

### Auto-advance is correct-answers-only, and anything cancels it

A won round has nothing left to read on the card, so it advances itself after 1s. A lost one
never does — the two definitions now side by side are the entire value of the round.

**The cancel is what makes 1s safe rather than rushed.** Any `pointerdown`/`keydown`/
`wheel`/`touchstart`, captured on `document`, stops the timer; so does pressing a mark, and
so does `load()` itself, so a manual „următoarea" cannot leave a timer running into the next
question and skip it. The countdown is drawn as a draining bar on the button rather than a
separate widget — the thing that is counting is the thing you press to stop waiting.

### On a phone, this page hides the footer and drops its nav labels

Both are `body.page-ghici`-scoped and both are exceptions to rules that hold everywhere
else, so they are worth stating. The footer goes because it is ~76–96px carrying nav and
display toggles you do not act on mid-round; **`--statusbar-h` must go to 0 with it**, since
`body`'s padding and the detail sheet's `bottom` both read that token and would otherwise
leave the height behind as dead space. The top nav keeps icons only *here alone* — the pass
that put those labels back exists because a bare glyph row is unreadable, but this is the
one bar that also carries a mode switch, a score and a leaderboard button, and at 390px the
bar wanted ~460px.

## Share metadata for `?word=` — `share_meta()` in `_lib.php`

A word link is the site's main shareable unit. Until 2026-08-12 it carried **no** metadata:
`?word=` was read only by `app.js`, after load, so every link ever posted previewed as the
generic site card and a crawler saw none of the 18,270 words. `index.php` now fills
`<title>`, `description`, `canonical`, the `og:*` set and `twitter:card` from the database;
the panel is still opened client-side, this is only the head.

- **`share_meta()` returns `null` for anything not in the table**, and the page falls back
  to its own titles. That is what keeps `?word=<junk>` inert rather than reflecting an
  attacker's parameter into `<title>` and `og:url` — the fallback is the security property,
  not just a nicety.
- **`site_origin()` derives the absolute origin** rather than hardcoding `voroave.ro`, so a
  subfolder deploy and a local `php -S` both emit URLs that resolve — same reasoning as
  `BASE`. `HTTP_HOST` is attacker-supplied and ends up in a URL crawlers follow, so it is
  whitelisted against a character class before being echoed.
- **The POS prefix comes out of the excerpt's budget, not on top of it.** Added afterwards
  it pushed `văz` to 187 characters and the preview cut mid-word wherever the reader's
  client chose. Checked across all 16,484 words with a definition: none over
  `SHARE_DESC_MAX`.
- **`share_excerpt()` strips the literary citation.** Definitions carry quotes
  („…SADOVEANU, O. I 452."), and in 160 characters they crowd out the meaning.

Playlists (`?w=`) deliberately still get the site default — a list has no one headword, and
inventing a title for it is a separate decision.

Pinned by `tests/test_share_meta.js`.

### A share lands on the word — the list behind the panel included

**The panel was never filtered and must stay that way.** `api/word.php` is a bare
`SELECT * FROM words WHERE word = ?` and `build_word_filter()` has never been anywhere
near it, so no control in the sheet — seam included — can suppress a shared word.

What *was* filtered is everything around it. 15,803 of the 18,270 words are outside the
default view, **11,193 of them on the seam alone**, so a shared `curiosity` word opened
over a list that did not contain it: close the panel and the reader was on a page whose
rail named filters they never set as the reason the word had gone. Since 2026-08-13 two
halves fix that, and **neither is sufficient alone**:

- **`share_relax_params()`** (`_lib.php`) makes the word *eligible*. It reads the row and
  returns which of the sheet's own defaults are hiding it —
  `['seam' => 'relevant,curiosity', 'variants' => 'show']` — computed from `class_modes()`,
  the same table `build_word_filter()` filters on. `index.php` emits it as
  `OTIOS_SHARE_RELAX` and `applyUrlToForm()` ticks exactly those controls before htmx
  fires the first search.
- **`pin_order_sql()`** makes it *visible*. Measured on the current build, with the seam
  relaxed a `curiosity` word ranks **2,468–13,660** under the default `populare` sort, and
  `PAGE_SIZE` is 250 — relaxing alone moves the row into a result set nobody scrolls to.
  The pin is prefixed ahead of `demote_order_sql()`, so a curator-demoted word someone
  shared still arrives on top.

Five things to keep:

1. **Relax the control; never inject the row.** The obvious shortcut is `OR word = ?` in
   the WHERE, and it is the mirror image of the bug: a list containing a word its own
   controls say it should not, with nothing on the page to explain it. Relaxing puts
   „ambele liste" / „cu variante" in the rail *and* a removable chip in the chip bar, so
   the wider list is both explained and undone in one click. The pin stays in the ORDER BY
   for the same reason — it moves a row the filters already admit, never admits one.
2. **The seam is added, never swapped** (`relevant,curiosity`). Arriving at one curiosity
   word is not a reason to take the default list away from a first-time visitor.
3. **An explicit param in the URL wins**, including a superseded spelling that already
   landed on the control (the `alias_*` flags in `applyUrlToForm()`). A link shared *with*
   filters on it shared the filters too — and since `syncUrlFromForm()` writes the form
   state back, that is what most shared links carry.
4. **`editorial` is left alone**, because `back` demotes rather than hides — the word is in
   the list already, and the pin is what makes it reachable.
5. **The pin rides in a hidden input inside `#filter-form`**, so htmx sends it with
   the first search and `next_url` carries it into every load-more. That is what makes it
   one global order — applied per page instead, the word would head page 2 and page 3 as
   well. `closePanel()` and the reload branch both clear it, since that is the moment the
   URL stops naming the word.

   **It posts as `pin`, never as `word`, and that is the whole of a real outage.**
   `hx-include` is one of htmx's *inherited* attributes, so `#word-list`'s
   `hx-include="#filter-form, #search"` applies to every `.word-row` inside it — a row's
   own request is `api/word.php?word=<its word>`, and the form appended a second, empty
   `word=` behind it. PHP keeps the last occurrence, so the panel endpoint saw `''`,
   answered 400, and **no word on the site opened its definition any more** — from a diff
   that never mentions `word.php`. Anything new put in this form has to be checked against
   the params the *rows* send, not only against `build_word_filter()`'s. Pinned by
   `tests/test_share_view.js` §9, which asserts both the input's name and that a row's URL
   survives the form riding along with it.

`word_scope()` is not involved: it never reads `word`, so a share is not a third scope
alongside `q` and `w=`. It is the ordinary filtered list with two of its own controls moved
and one row lifted to the top. Pinned by `tests/test_share_view.js`.

## Clean URLs — `public/.htaccess`

`/despre` serves `despre.html`, `/metodologie` serves `metodologie.html`. Both are plain
`.html` now; the rewrite tries `$uri.php` first and then `$uri.html`, so neither needed a
rule of its own. Two rewrites, each
firing only when the requested path is not already a real file or directory *and* the
extension-ful version exists, so nothing that resolves on its own is touched. No
`RewriteBase`: every condition tests `%{REQUEST_FILENAME}`, which Apache has already
resolved to an absolute path, so this works at any URL depth.

**There is deliberately no redirect from `/despre.html` back to `/despre`.** It would look
tidier and it would break the app: every API call goes to an explicit `api/*.php` and
several are POSTs (`sync`, `lists`, `profile`, `game`). A 301 on a POST is not required to
preserve the method and browsers historically turn it into a GET, so the write silently
becomes a read. Excluding `/api/` would work but makes the file a list of exceptions the
next endpoint has to remember to join. Both spellings resolve; each page names the slug in
its `<link rel="canonical">`.

**`php -S` ignores `.htaccess`**, so local dev would 404 on every slug and a broken link
would ship unseen. Use the router:

```bash
php -S 127.0.0.1:8011 -t public tools/dev-router.php
```

It mirrors those two rules and nothing else, and lives in `tools/` on purpose — only the
contents of `public/` are deployed, so a router placed there would be reachable over HTTP.

**On nginx** the equivalent is `try_files $uri $uri.php $uri.html $uri/ =404;` alongside
the `location ~ \.(db|db-wal|db-shm|sqlite3?)$ { deny all; }` block the deploy section
already requires.

## Deploying to a subfolder

The app runs at any URL depth. `BASE` (`api/_lib.php:8-13`) is derived by subtracting
`DOCUMENT_ROOT` from the real path of the app folder, and everything — assets, links,
htmx endpoints, `OTIOS_BASE` for JS — is prefixed with it.

Copy the **contents of `public/`** into the target folder. The production layout is a
**root** deploy on `voroave.ro`; the subfolder case is what the rest of this section is
about, because it is the one where `BASE` does any work.

```
~/voroave.ro/             ← document root — contents of public/
├── index.php  api/  assets/  data/ui.db
└── api/config.local.php
~/voroave-private/        ← OUTSIDE the web root
└── app.db  secret.key  backups/
```

```
~/lab.gov2.ro/            ← subfolder variant: document root
└── oțios/                ← contents of public/   →  lab.gov2.ro/oțios/
```

Five things that bite:

1. **Never deploy the repo itself**, only `public/`. With the repo mounted, `private/app.db`,
   `.git/config` and the docs are all straight downloads — measured.
2. **Where `app.db` lands by default depends on which layout you are in, and only one of
   them is dangerous.** `OTIOS_PRIVATE_DIR` defaults to one level up from the app folder.
   On the **root** deploy that is `~/private/` — outside the web root, so safe, just untidy.
   On a **subfolder** deploy one level up *is the document root*, so the default puts
   `app.db` at a public URL. Either way, set it explicitly: copy
   `api/config.local.example.php` → `api/config.local.php` (gitignored; `_appdb.php:18`
   loads it if present) and set:
   ```php
   define('OTIOS_PRIVATE_DIR', '/home/you/voroave-private');
   ```
   **Moving an existing install moves three things, not one:** `app.db`, `secret.key` and
   `backups/`. `secret.key` is the one people drop — it seals quiz `qid` tokens and admin
   sessions, and `private_dir()` silently generates a fresh one when it is missing, which
   errors out any player mid-round and logs you out of `admin.php`. No data is lost, but
   carrying it makes the move invisible.
3. **Never overwrite the server's `config.local.php` with yours.** It is per-install, and
   local dev has one too — different private dir, different admin token. Always exclude it:
   ```bash
   rsync -av --exclude 'api/config.local.php' public/ you@host:~/voroave.ro/
   ```
   The file being gitignored protects the repo, not a careless `rsync`.
4. **No `Alias`, no symlinks.** `__DIR__` resolves symlinks and `DOCUMENT_ROOT` does not, so
   the subtraction silently produces garbage rather than failing — an Apache `Alias` was
   measured yielding `BASE = "blic"`. The folder must sit physically inside the docroot.
   Verify by viewing source and checking `var OTIOS_BASE`.
5. **On nginx**, add `location ~ \.(db|db-wal|db-shm|sqlite3?)$ { deny all; }`. The
   `public/data/.htaccess` that hides the 20 MB `ui.db` is Apache-only.

Non-ASCII folder names work (`/oțios/`), but see `cookie_base_path()` in `_auth.php` for
why the cookie path has to be percent-encoded — the cookie *is* the account, and a Path the
request URI can't match means a new anonymous user on every request.

## Out of scope

- **Web UI / API** — mentioned in roadmap Phase 5; do not start without explicit go-ahead.
- **Database server** — SQLite is sufficient. No Postgres.
- **Embeddings / heavy ML** — pipeline is deliberately frequency-based and cheap to re-run.
- **PyPI packaging** — loose scripts are fine.

## Monitoring

Three scripts keep an eye on long-running corpus jobs:

- **`status.py`** — read-only, at-a-glance summary. Prints corpus run state, pipeline artifacts, loop liveness, and latest audit verdicts. Safe to run any time; never writes. First thing to run when checking on the project.
- **`health_check.py`** — checks loop liveness, checkpoint staleness, log errors, and corpus completion. Alerts once per new problem (no spam on repeat cron fires). Run every 30 min via cron.
- **`audit.py`** — snapshots run history to `data/logs/run_history.jsonl` and runs quality checks (cycling detection, token ratio sanity, word coverage). Run daily.

`health_check.py` and `audit.py` support `--dry-run`. Alerting backends (set env vars before running or in crontab):
```bash
export OTZIOS_ALERT_URL="https://ntfy.sh/your-topic"   # POST plain text — works with ntfy.sh, many webhooks
export OTZIOS_ALERT_EMAIL="you@example.com"             # sends via system mail
```

Cron entries (install with `crontab -e`):
```cron
*/30 * * * * cd /home/pax/g2-dev/otzios && /home/pax/g2-dev/monitorulpreturilor/venv/bin/python health_check.py >> data/logs/health_check.log 2>&1
0 2 * * *   cd /home/pax/g2-dev/otzios && /home/pax/g2-dev/monitorulpreturilor/venv/bin/python audit.py         >> data/logs/audit.log      2>&1
```

Update `VENV` to `.venv/bin/python` after the in-project venv migration.

### Venv migration (deferred — after culturax finishes)

```bash
cd /home/pax/g2-dev/otzios
python -m venv .venv
source .venv/bin/activate && pip install -r requirements.txt
# then update crontab VENV path and restart any loops
```

## Process notes

- When something needs follow-up, add a `- [ ]` entry to `docs/BACKLOG.md` with enough context to act on later.
- After meaningful work, add an entry to `docs/activity-history.md` under `## YYYY-MM-DD — Short Title`.
