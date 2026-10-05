# Backlog

Open bugs, debt, and enhancements. Add new entries with `- [ ]` and enough context to act on later.

The [audit handoff](fixes/README.md) is the current execution queue. Its briefs define acceptance.
Checkboxes describe status; dated investigations below preserve evidence from earlier builds.
An old note is not a current measurement. Do not duplicate the same task in several sections.

---

## Bugs / Known Issues

### Project audit — 2026-10-05

- [ ] **P1: Live synonym searches return HTTP 500.** [Implementation brief](fixes/F01-synonym-deployment.md). The landing page loads, but
  `/sinonime?q=frumos`, `?q=repede`, `?q=văz`, `/sinonime.php?q=frumos`, and
  `/api/syn.php?q=frumos` fail. Local synonym tests pass against the checked-out
  databases. Inspect server logs and verify `public/data/syn.db`, its schema,
  permissions, and deployed PHP capabilities. The root cause is not yet established.
  Add a production smoke check that searches a word; testing the landing page misses this.

- [ ] **P1: Sync drops newer edits made during an earlier push.** [Implementation brief](fixes/F02-sync.md). Reproduced with
  the real `store.js` in a VM and a delayed response. Edit `zapciu`, start `syncNow()`,
  edit it again, then resolve the first request. The pending queue becomes empty,
  although the newer note was never sent. `store.js:425` deletes snapshot keys without
  comparing their current revision. Keep changed entries queued and schedule another push.
  Also acknowledge only accepted changes: `sync.php` truncates requests at 5,000,
  while the client clears its entire snapshot and ignores `rejected`.

- [ ] **P1: The sense quiz exposes answers in structured definitions.** [Implementation brief](fixes/F03-quiz-spoilers.md). Confirmed
  on the live desktop and mobile pages before answering. `ghici.php:434` masks
  `.definition-text`, but `detail.php` now renders `.fp-senses` and `.fp-extras`.
  These blocks, citations, and synonym hints remain visible. Extend the spoiler
  policy to the full answer content. Verify structured and flat definitions separately.

- [ ] **P2: `/stats` collides with the hosting provider's traffic report.** [Implementation brief](fixes/F04-statistics-route.md). Live
  `/stats` returns “voroave.ro Web Server Statistics”; `/stats.php` returns the app.
  A real directory wins over the extensionless rewrite. F04 selects `/statistici` for the app;
  verify navigation and canonical URLs. Review hosting-report access as a separate owner operation.

- [ ] **P2: `/despre` has an invalid preference boot script.** [Implementation brief](fixes/F06-about-preferences.md). In
  `public/despre.html:25`, a `// before 2026-08-14` comment consumes the rest of
  the single-line script. Chromium reports a syntax error. Remove the comment
  or use a block comment. Verify saved theme, skin, and text scale on direct arrival.

- [ ] **P2: Shared word links lose structured senses.** [Implementation brief](fixes/F05-shared-definitions.md). Confirmed with
  `/?word=zapciu`: first arrival shows a flat definition with pipe-separated citations.
  Clicking the word loads three structured senses. `index.php:550` passes only
  `w` and `ssr`; `api/word.php` loads senses and citations too. Share the data-loading
  path so both renderers receive the same content.

- [ ] **P2: Define a repeatable current-project test command.** [Implementation brief](fixes/F07-test-harness.md). Python tests under
  `tests/` pass: 222 tests. Unscoped pytest also collects archived Flask tests:
  261 passed, six failed. Twelve local API suites passed; `test_store_sync.js`
  failed because its hardcoded words `abecedar` and `zăbavă` are absent from `ui.db`.
  The quiz DOM suite skips successfully when `jsdom` is missing. Declare JS test
  dependencies, use durable fixtures, and make required-suite skips visible.

- [ ] **P2: Build `ui.db` through a validated temporary artifact.** [Implementation brief](fixes/F08-atomic-build.md).
  `tools/build_ui_db.py:1003` unlinks the previous output before building its replacement.
  A later failure leaves a partial build and removes the last good artifact.
  Validate required inputs, schema, integrity, and stable IDs before replacing the output.

- [ ] **Ranking evaluation protocol** — [F09](fixes/F09-evaluation.md). Planning/sample only; no production scoring change.

- [ ] **Recovery decision and backup verification** — [F10](fixes/F10-recovery.md). No account merge or production restore.

- [x] **Reconcile current documentation and prepare delegation briefs** — completed 2026-10-05.
  Current README/guide, dated historical notes, corrected public methodology, and F01–F10 handoff.
  Application fixes and operational verification remain open.

### Earlier findings

- [ ] **`.fp-dicts` (the "în N dicționare" row) can sit below `.fp-body`'s scrollable
  fold, out of reach without scrolling first.** Found 2026-08-18 while reproducing the
  `.dict-tooltip` off-canvas bug (fixed the same day — see `docs/activity-history.md`).
  `.fp-body` has a fixed clip height (44vh on desktop, 60vh on a phone); `.fp-dicts`
  renders last, after the sense tree, synonyms and tags, so a long multi-sense entry can
  push it partly or fully past the visible/clickable area — `getBoundingClientRect()`
  still reports its true layout position, so a click aimed at "where the button should
  be" can land on whatever's actually painted there instead (measured: the page footer,
  or the next section down), while a click on the sliver that IS visible still works.
  Not new — predates both the senses feature and the transform fix — and not what the
  reported screenshot showed (`bidinea` is short, the toggle was fully visible, just
  mispositioned). Getting worse now that entries commonly carry 2+ senses with citations
  and synonym chips. No fix attempted yet; candidates are unclear (taller default panel
  height fights the "don't cover more of the list than needed" reasoning already
  documented for 44vh/60vh; scrolling `.fp-dicts` into view on open is plausible but
  would need to not fight a reader who scrolled somewhere else on purpose).

- [ ] **Historical corpus is thin — 19.4M tokens against the modern panel's 17.0B, a
  876× asymmetry** (re-measured 2026-08-18: `wikisource_ro` 14,297,033 + `lumro_ro`
  5,072,239 vs `culturax_ro` 16,969,999,321). This is the project's **most load-bearing
  signal measured on its thinnest data** — `SCORE_HIST` is worth up to 25 points, tying
  `SCORE_MODERN` for the largest band, and `make_shortlist.py` says why in its own
  comment: without it the top of the list fills with words that were never in
  circulation. Corollary worth acting on: **more modern web text buys nothing** (CulturaX
  at 17B already resolves far below wordfreq's floor — that is how `modern_band` separates
  `zapciu`'s 1,322 from `celșag`'s 0), while any historical text moves the ranking
  directly. Prefer **newspapers over novels**: a novel is one writer's vocabulary, which
  is the same reason LUMRO's `document_count` is authors and not novels. See
  `docs/archive-obsolete/wordfreq-recipe.md` §5–6 for the corpus shortlist (DigiBuc, BCU Cluj, Gutenberg RO)
  and §3–4 for why the additions should feed **corroboration counts, not a wordfreq-style
  trimmed mean**. Wikisource gives one occurrence =
  0.07 ppm, so the whole historical side rests on very few hits: 9,996 shortlist words
  (40%) sat on ≤2 occurrences before the 2026-08-08 rescore added `HIST_MIN_OCC`/
  `HIST_MIN_DOCS` floors. Those floors make the signal honest but they cannot create
  evidence — words genuinely used in 1880 but absent from Wikisource still read `absent`.
  This is now the largest remaining source of error. Options: more Romanian literature
  (archive.org, Gutenberg RO), the DLR/DLRLC literary citations already embedded in the
  dump's definition text (`GALAN,`, `CARAGIALE`, `DUMITRIU, N. 122` — a free, dated,
  in-repo citation corpus), or CoRoLa. The citation route is cheapest and worth costing
  first.

- [ ] **CLRE (`clre.solirom.ro`) — DCR3 (9,424 entries, real text+citations) and TDRG3
  (33,322) are usable public sources; DCR2 is redundant; the rest of the ecosystem is
  facsimile-only.** Checked 2026-08-17–18, both `dexonline.ro/surse` (confirms DEX '84,
  DEX '75, all 19 `DLR` volumes, DCR3, MDA, DEXI etc. sit at <5% ingested there — stub
  text, matching the `internalRep`-truncation finding) and the live CLRE sites directly, by
  reading each site's JS (`js/index.js`, the `<solirom-editions>` tag) for its backend URL
  and fetching `indexes/text/cross-references.json` + a sample entry with `curl`. Nine
  dictionaries are actually live (not just catalogued): `dex1`, `dl`, `dm`, `dlr1`, `nv`
  (=Negulici's 1848 vocabulary) at `<name>.solirom.ro`, plus `tdrg` (=TDRG3), `dcr2`, `dcr3`
  at `solirom-clre.gitlab.io/texts/<name>/site/`.

  **My first pass wrongly wrote off DCR2/DCR3 as GitLab-login-gated — correct the record.**
  I'd tested `texts/dcr2/` (no trailing segment) and gotten a 302 to a GitLab OAuth check,
  and assumed the whole project needed a login. The real published app is one level
  deeper, at `texts/dcr2/site/` / `texts/dcr3/site/` — genuinely public, no auth, no
  session, confirmed with cold `curl`. The 302 on the bare path is the same "unmatched path
  falls through to the domain's gated default project" behavior seen elsewhere on this
  host, not a property of the dcr2/dcr3 projects themselves. Lesson: a 302 to
  `projects.gitlab.io/auth` on a *directory* path doesn't prove the content is gated —
  check the site's own `<solirom-editions data-url>` for the real backend root before
  concluding that.

  **Two backend shapes, and they are not equivalent:**
  - `dex1` (65,758 entries), `dl` (37,248), `dm` (48,691), `dlr1`/DA-DLR (144,081), and `nv`
    (6,552, mixed) mostly resolve a headword to a **scanned facsimile page image** (`<img>`
    of a `.webp`/`.png`), not transcribed text — the "digitization" is a headword→page
    index, nothing OCR'd (e.g. `dm`'s `abager` → `texts/dm/facsimiles/f0007.webp`). Not
    usable as a text corpus without running OCR ourselves, and even then it's 1913–1948
    typography, or for `nv` 1848 Romanian-Cyrillic.
  - `dcr2`, `dcr3`, `tdrg` (and some `nv` entries) are the opposite: real transcribed text
    per entry, `curl`-able as `solirom-clre.gitlab.io/texts/<name>/text/{id}.html`, where
    `{id}` comes from that dictionary's own `indexes/text/cross-references.json`
    (`[[headword, id], ...]`).
    - **`dcr3`: 9,424 entries**, full text with dated press citations —
      `AH1N1` cites `R.l. 9 X 09` (România liberă) and `G. 29 X 09` (Gândul) — versus the
      **~183 CLAUDE.md documents as visible on dexonline.ro itself**, where "no word page
      renders a DCR3 definition." This is a real, previously-undocumented gap-filler for
      exactly the source this project's own docs currently call "nothing to scrape yet."
    - **`dcr2`: 5,770 entries**, same shape (`ADN` cites `R.l. 12 V 83`, `Cont. 9 XII 83`).
      Close to but not identical to the 5,807 `extract_dcr.py` already recovers from the
      DEX dump's `Meaning` tree — **likely redundant** with what the project already has,
      though never cross-checked; could be useful as a faithful-per-source second opinion
      where the dump's merged sinteză text is suspected of mixing sources (the same reason
      `scrape_dcr.py` exists).
    - `tdrg` (TDRG3, Tiktin's Romanian-German dictionary, ed. Miron/Lueder): TEI-XML with
      `<sense>`, gloss, etymology, and a literary citation with bibliography
      (`Agatanghel` cites `AL. OP. I, 1231` — Alecsandri, volume+page). Genuinely new
      source, nothing comparable in the current pipeline — but **not dated in the
      citation itself** (no day/month/year token, unlike DCR), so using it for the
      diachronic pipeline needs an author/work→year table first — the same unsolved
      problem the `GALAN,`/`CARAGIALE`-style dump citations already have, not a new one.
      No sigla/bibliography legend page found on `tdrg.solirom.ro` (`about.html` and
      `word-lists.html` are both literally "Pagină în lucru").

  **DCR2/DCR3 citations parse cleanly — checked against the real legend, not guessed.**
  `dcr3/site/static/peritexts/front/bibliography.pdf` ("SURSE") is a ~200-entry siglum
  legend, e.g. `R.l. – „România liberă", ziar, București, înainte și după 1990` — the
  "before/after 1990" note is exactly what resolves the 2-digit year's century. Sampled 8
  random `dcr3` entries beyond the two above and the citation shape holds, with three
  variants a parser needs to handle: `{siglum} {D} {roman-month} {YY}` (newspapers,
  `R.l. 3 X 07 p. 10`), `{siglum} {issue}/{YY}` (magazines, `Atac 48 / 98 p. 15`,
  `L. Mag. 12 / 94 p. 42`), and bare cross-references with no siglum at all
  (`v. și show (show-business) 1994`). Web-only sources use their domain as the siglum
  (`wall-street.ro 20 V 06`), also listed in the same legend. `abbreviations.pdf` at the
  same path is grammatical (adj., adv., …), not the source sigla — don't confuse the two.

  **This is CDN-served static content, not a community server — the dexonline politeness
  norm doesn't map over as-is.** 8 sequential fetches across random `dcr3` ids took 6.4s
  total (~0.8s/req) with no throttling observed; GitLab Pages is Fastly/Cloudflare-backed
  and built for burst traffic. Still worth a modest delay and a lock file out of general
  courtesy on a real run, but there's no dexonline-style "community-run, be gentle"
  reasoning to import wholesale — say so explicitly if `scrape_clre.py` ever gets written,
  so nobody copies the 3s dexonline delay here for the wrong reason.

  - **Done (2026-08-18): `scrape_clre_dcr.py` written and tested, both editions** — see
    `CLAUDE.md`'s DCR section for the run commands and output shape
    (`data/processed/clre_dcr_definitions.csv`/`.db`, kept separate from
    `dcr_definitions.db` on purpose). `dcr2` was included despite the "probably redundant"
    call above, per explicit ask — it's cheap to pull alongside `dcr3` and stands as the
    faithful-per-source second opinion either way. Not yet done: parsing the citations into
    `(source, year)` pairs and deciding how (or whether) this feeds `definitions.db` /
    `make_shortlist.py` — right now it's a raw scrape artifact, same stage
    `dcr_definitions.csv` was at before anyone wired it further in. `tdrg` (bigger, but
    needs an author→year table before its citations are usable for dating) is still just
    scoped, not built. `robots.txt` on both gitlab.io hosts just 302s to the same GitLab
    auth check as everything unmatched at their root (no explicit policy either way);
    `tdrg.solirom.ro` itself serves an empty allow-all `robots.txt`. No terms-of-use page
    found anywhere in this ecosystem. Still unchecked: how (or whether) `dcr2`/`dcr3`'s
    `A0000xx`-style ids map to the dump's own entry ids — probably moot, since matching by
    normalized headword is sufficient and both sources give one.

- [ ] **`modelType 'V'` is missing from the corpus lookup allow-list** (găsit 260810).
  `load_dex_words()` — în `process_wikisource.py`, `process_culturax.py` și acum și în
  `process_lumro.py`, copiat verbatim — acceptă `modelType IN ('A','F','M','N','VT','VI',
  'IL','PT','P')`. `'V'` lipsește, deși `'VT'` și `'VI'` sunt acolo: sunt toate verbe.
  Efect: **3.184 de leme cu `modelType='V'` și `description` goală nu sunt numărate în
  niciun corpus** — `râde` (frecvență DEX 0,99!) e complet absent din tabelul `culturax_ro`.
  Impact măsurat pe shortlist: **un singur cuvânt** (`țepeni`, `absent` cu 0/0), pentru că
  lista curată filtrează oricum aproape tot restul — deci e de reparat, nu urgent.
  De verificat cu ocazia asta și `'I'` (invariabil, 25.999 fără descriere) și `'SP'` (1.081):
  `'T'` e exclus intenționat (formă flexionară, nu headword), dar `'IL'` — la fel de
  flexionar — e în listă, deci allow-lista nu e coerentă cu ea însăși.

- [ ] **Variant detection only catches paradigm-sharing pairs.** `family_ratio` (see
  `make_shortlist.FAMILY_RATIO_VARIANT`) flags `politeță`/`politețe` and `uleu`/`ulei`
  because they share inflected forms. Phonetic respellings with unrelated paradigms —
  `vivliotică`/`bibliotecă`, `tăligraf`/`telegraf`, `sâroman`/`sărman` — are invisible to
  it, and are currently only kept out of the relevant seam by having no current
  dictionary. A phonological-correspondence matcher (`v→b`, `tăli→tele`, `î/â`) against
  corpus-alive lemmas would close the gap.

  **Sized 260811, and it is the biggest quality problem left.** Măsurat cu CoRoLa ca punct
  intermediar în timp (vezi mai jos): **5.419 de cuvinte din shortlist (30,8%)** cad între
  corpusul de referință și cel web, iar inspecția arată că bucket-ul e dominat nu de
  vocabular pierdut, ci de **grafii vechi ale unor cuvinte foarte vii**:

  | pe shortlist | culturax | perechea modernă | culturax |
  |---|---:|---|---:|
  | `țeară` | 527 | `țară` | 5.764.577 |
  | `răpede` | 913 | `repede` | 2.914.729 |
  | `biurou` | 317 | `birou` | 1.227.238 |
  | `obicinuit` | 740 | `obișnuit` | 954.491 |
  | `strein` | 1.924 | `străin` | 584.968 |
  | `poroncă` | 228 | `poruncă` | 111.044 |

  **Prima felie livrată 260811: `archaic_spelling`** (`mark_archaic_spellings()` în
  `tools/build_ui_db.py`) — 291 de cuvinte, 110 din vederea implicită, cu `spelling_of`
  arătat în panou („Grafie veche pentru *situație*"). Reguli **deliberat înguste**, doar
  cele măsurate curate: `-țiune/-ziune/-siune`, `sb/sd/sg → z`, `des+voiced → dez`,
  `adv → av`, fiecare cerând un geamăn numit de ≥20× mai frecvent în corpusul modern.
  Auditate manual: 0 fals-pozitive vizibile din 47 de non-`-iune`.
  **Regulile generale au fost măsurate și respinse**: `e → ă` trage de 2.300 de ori pentru
  69 de perechi și ar echivala `peți` cu `păți` — cuvinte diferite; la fel `iu → i`
  (`albiu`/`albi`) și `-ea → -a` (`zaharea`/`zahara`). Un flag care ascunde are
  fals-pozitive invizibile, deci precizia bate acoperirea.
  **De NU lărgit** la „tot ce cade între CoRoLa și CulturaX": populația aia e de 5.421 de
  cuvinte, 61,6% din vederea implicită, și e plină de găsiri reale (`acaret`, `afion`,
  `agie`, `alișveriș`, `amploiat`).

  Rămâne deschis restul: `strein`/`străin`, `țeară`/`țară`, `poroncă`/`poruncă`,
  `biurou`/`birou` — corespondențe vocalice neregulate, care cer altceva decât reguli de
  sufix. `variant_like` prinde **3,3%** din ele, fiindcă perechile astea nu împart paradigmă
  (`strein`/`străin` au radicali diferiți). Nu e nevoie de CoRoLa ca să le detectezi —
  CulturaX singur arată raportul. E nevoie de **generarea candidatului**: reguli
  fonologice (`ea→a`, `o→u`, `iu→i`, `e→ă`, `-țiune→-ție`, `ct→pt`) plus testul „perechea
  e de N ori mai frecventă în corpusul modern". CoRoLa a servit doar la a scoate populația
  la suprafață.

- [ ] **`oțios` sits in the `curiosity` seam.** Score 67: zero historical corpus
  attestation, 266 modern occurrences. Correct by the current rules, awkward for the
  project's namesake. Decide whether the naming question moves, or whether the
  no-corpus-signal (`dex_absent_highfreq`) class deserves its own treatment.

- [ ] **CLRE (clre.solirom.ro) spike — timeboxed.** 100 dictionaries aligned at entry and
  sense level, free access, from the "A. Philippide" institute. Deferred in the
  2026-08-08 audit because dexonline already yields 113 sources covering the same
  historical spine (Scriban, Șăineanu, CADE, DAR, DLR, DLRLC, MDA2), and `Source.year`
  supplies the recency signal CLRE would have been used for. Its unique value is
  *first-attestation dating* and dictionaries dexonline lacks (Lexiconul de la Buda 1825,
  Laurian–Massim 1871). No documented bulk export — check for one before building on it.

- [ ] **`extract_lexemes.py` still uses the lossy regex splitter.** `re.findall(r'\(([^)]+)\)')`
  drops rows containing a literal `)` in a quoted field. Measured impact is small — 33 of
  317,721 rows (0.01%), *not* the 13% first estimated from the AUTOINCREMENT high-water
  mark — so this is tidiness, not urgency. `dump_parser.parse_tuples` is the drop-in
  replacement and `extract_inflected_forms.py` already writes a complete `lexeme` table
  that could replace `lexemes.db` outright.

- [ ] **`create_curated_list.fetch_all_tags` misses root tags 6 (`rar`) and 239
  (`ieșit din uz`).** It walks parents `{1,17,41,42}` while
  `validate_diachronic.load_taxonomy` also catches `{6,17,239}`. So `dex_register` in the
  curated CSV is strictly narrower than in the diachronic one, which weakens
  `validate_with_wordfreq.py`'s archaic-register gate — it can never see two of the four
  markers in its own `ARCHAIC_REGISTER_MARKERS`.


- [ ] check why some words are still missing definitions even if found on dexonline. did scraping fail?
  Scale as of 2026-08-08's `ui.db`: **746 of 16,315 words have no definition, 33 of them
  in the `relevant` seam.** Small enough to diagnose case by case rather than guess.

- [x] **`scrape_definitions.py` has no host lock.** — **Fixed 260810.** `acquire_host_lock()`
  + the `LockHeld` branch copied in, guarded on `not args.dry_run` (and `--merge-only` already
  returns before it), locking the same `data/.dexonline.lock` path. Verified cross-script: with
  `scrape_synonyms` holding the lock, a live `scrape_definitions` run exits 1 naming the holder
  while `--dry-run` still prints its queue. Duplicated rather than imported, per the convention
  below — **the lock *path* is the contract**, so if it drifts in one file the two silently stop
  interlocking; that is the line to watch, and the point to lift it into a shared module is when
  a third caller appears. Original note follows.

  `scrape_synonyms.py` got one on
  2026-08-08 after two copies of it ran concurrently and halved the interval between
  requests, which is the one thing `--delay >= 3` exists to prevent. The lock is keyed on
  the **host** (`data/.dexonline.lock`), not on the script, precisely so the definitions
  scraper interlocks with the synonyms one by adopting the same two lines —
  `acquire_host_lock()` / the `LockHeld` branch in `main()`. Until it does, running both
  at once reproduces the bug across scripts. If a third caller appears, that is the point
  to lift the helper into a shared module rather than copy it a third time.

- [ ] `dreadnought` nu e marcat ca `marină` (Mar.) in our UI but it is in dexonline web

- [ ] **`rare_in_use` tier is polluted by modern loanwords + proper nouns** — the UI "rare" tab (`?word_tier=rare_in_use`) shows words that aren't rare: English borrowings (`screening`, `meeting`, `house`, `short`, `golden`, `dolby`, `wild`, `trend`, `scanner`, `cutter`), brand/variety names (`jonathan`), and proper nouns (`sioux`, `zulu`, `hagi`, `viking`). Two failing signals:
  1. **Low DEX `frequency` ≠ rare.** `create_curated_list.py:127-129` selects `0.01 < frequency < 1.0`; DEX `frequency` is editorial-coverage, not corpus frequency, so recent borrowings land in that band (`screening` 0.27, `meeting` 0.71, `house` 0.81) while still being everyday words.
  2. **Register gate too permissive** (`validate_with_wordfreq.py:151`): admits a word on `zipf < 4.5 AND dex_register non-empty` — *any* tag. Of 582 rows in `rare_words_wordfreq.csv` only ~124 are `învechit`; the rest are stylistic tags (`figurat` 172, `popular` 82, `familiar` 59, `livresc` 39) — exactly what colloquial loanwords carry. The gate was meant to require an *archaic* marker.

  Compounding: no loanword filter (some borrowings hit zipf 4.0–4.5, e.g. `house` 4.36, `jonathan` 4.25; `dex_etymology` is empty in the CSV so etymology filtering needs re-extraction); the proper-noun filter `create_curated_list.py:69-72` checks `word[0].isupper()` but the data is lowercased so it never fires; even `învechit` rows are noisy from homograph mismatches (`cannabis`→`învechit`, `listat`→`învechit`); 28 duplicate `word_no_accent` rows (e.g. `house` as `s.n.` and `adj.`). Loaded by `ui/app.py:122-144` (tier set at `app.py:142`). Sharpens enhancement #12. Fix options: (a) restrict the register gate to archaic markers (`învechit` + combos); (b) add a cross-lingual English-zipf loanword filter; (c) fix the proper-noun filter to run on cased DEX forms; (d) dedup by `word_no_accent`. Regenerating `rare_words_wordfreq.csv` means re-running `validate_with_wordfreq.py`. **Exploratory UI path added 2026-05-28** (see activity-history): the detail panel now shows zipf/en/dex/dict-names per word, and reversible filters (zipf range, dex range, hide-loanwords via `en_zipf`, hide-proper-nouns via DEX casing) let us triage interactively before deciding what to make permanent. Options (b) and (c) are now prototyped as UI toggles in `ui/app.py::_enrich_words` / `extract_dict_sources.py`.

  **Partially resolved 2026-06-07** — pipeline options (a) + (d) done in `validate_with_wordfreq.py`:
  - **(a) Register gate restricted to archaic markers.** New `ARCHAIC_REGISTER_MARKERS` (`învechit`, `arhaizant`, `rar`, `ieșit din uz`) + `has_archaic_register()`; the `rare_in_use` gate now requires one of these instead of *any* non-empty register. New `--rare-register {archaic,any}` flag (default `archaic`; `any` restores legacy behaviour). On the current curated CSV this cut `rare_in_use` from **582 → 113** and removed `screening`/`meeting`/`house`/`jonathan`/`sioux`/`zulu`/`viking` etc.
  - **(d) Dedup by `word_no_accent`.** New `--dedup` flag (default on) collapses same-headword rows that differ only by POS (e.g. `house` as `s.n.` + `adj.`); dropped 10,133 duplicate rows on the current input.
  - **Still open:** (b) cross-lingual loanword filter and (c) cased proper-noun filter remain *deliberately* as reversible UI toggles (per the 2026-05-28 triage note) rather than permanent pipeline filters — promoting them is a product decision. Residual noise in the archaic-gated rare list is now dominated by **sense-level homograph mismatches** (`cannabis`/`listat`/`spray`/`court`/`hagi` carry an `învechit` tag on a different sense than the modern one); these are caught today by the UI's `hide_loanwords` (en_zipf) and `hide_proper` toggles. Takes effect on next `validate_with_wordfreq.py` run.

- [ ] **P0 — Phase 2 candidate-set mismatch** (`process_corpus.py:56-67,187,292` vs `validate_forgotten_words.py:64-70`): `process_corpus.py` only counts tokens in `forgotten_words_curated.csv` (~1.9k words), but the validator queries `lexemes.db` with `frequency > 0.01 AND frequency < 0.60 AND LENGTH(form) > 3` (tens of thousands of lexemes). Words absent from the curated CSV silently get `total_occurrences = 0` and are classified as `confirmed_forgotten` with confidence ~0.99. The "159,543 validated, 1 false positive" headline in `docs/phase2-test-results.md` is an artefact. Fix: align the candidate source, or have `process_corpus.py` count every token.

- [x] **Three competing MySQL→SQLite paths** — Fixed. `extract_lexemes.py` is the sole canonical path; `convert_to_sqlite.sh` + `mysql_to_sqlite.py` moved to `archive/` (with `archive/README.md` explaining why). Note: `docs/scripts-guide.md` still documents `mysql_to_sqlite.py` as an "alternative approach" — left for a separate docs pass.

- [ ] **`explore_dex.py` is dead code** — imports `sqlite3` but never uses it; `__main__` points `db_path` at a `.sql` file that `sqlite3.connect()` cannot open. Content is narrative; move to `docs/` or delete.

- [x] **Frequency-bin definitions disagree across scripts** — Fixed. Added `constants.py` as the single source of truth: `MIN_FREQUENCY`, `MIN_FORM_LENGTH`, the canonical rarity-bin edges (`VERY_RARE_MAX`/`RARE_MAX`/`UNCOMMON_MAX`) + a `rarity_category()` helper, plus the per-stage candidate ceilings (`CURATED_FREQ_CEILING`, and the clearly-marked legacy `ANALYZE_FREQ_THRESHOLD`/`VALIDATION_FREQ_CEILING`). `create_curated_list.py` now bins via `rarity_category()` (removed two duplicated inline binning blocks); `analyze_forgotten_words.py` and `validate_forgotten_words.py` import their floors/ceilings. Boundary-tested: new binning matches the old logic exactly at every edge. Legacy display histogram bins in `analyze_forgotten_words.py` are coupled to its 0.70 candidate threshold and left script-local (documented as intentional in `constants.py`).

- [x] **Regex probable typo in `create_curated_list.py:28-32`** — Fixed: removed trailing apostrophe from `r"^[a-z]+-[a-z]+'"` so the hyphenation filter now actually fires. Was dead code (matched 0 words in the shortlist).

- [ ] **OSCAR auth fails silently** (`process_corpus.py:255-261`) — when `--full` is requested but the dataset is unreachable, the run silently skips OSCAR. Should fail loudly or warn clearly.

- [ ] **`download_wikipedia_ro.py` blocks on interactive `y/N`** — not scriptable without a `--yes` flag.

- [ ] **No CLI path overrides** — all scripts hardcode `data/dictionaries/` and `data/processed/`; `process_corpus.py` has `argparse` for mode only, not paths.

- [ ] **Confidence-score weights are unjustified** (`validate_forgotten_words.py:215`) — `dex×0.3 + corpus×0.5 + doc×0.2` was chosen ad hoc. Treat output as ordinal, not absolute.

- [x] **`load_taxonomy()` join is wrong — domain/register/etymology columns are noise** — Fixed. `extract_taxonomy.py` now extracts `TreeEntry(id, treeId, entryId)` and `MeaningTree(meaning_id, tree_id)` into `lexemes.db`. Both `load_taxonomy()` in `validate_diachronic.py` and `fetch_all_tags()` in `create_curated_list.py` use the corrected join chain `Lexeme → EntryLexeme → TreeEntry → MeaningTree → ObjectTag(objectType=3)`. Verified: `pretutindeni` now has no tags (correct), `antipapă` → français etymology (correct), `isihie` → `învechit` register + neogreacă etymology (correct). **Re-run `validate_diachronic.py` to regenerate the shortlist CSV with accurate taxonomy columns.**

---

## Enhancements

- [x] **Show the full `sinteză` — every sense, not just the first.** Specced in
  `docs/senses-plan.md` (2026-08-18), built the same day. `extract_meanings.py` →
  `data/processed/meanings.db` (13,712 trees, 48,135 meanings, 14,413 citations, 10,024
  etymons); `merge_senses()` in `tools/build_ui_db.py` fills
  `senses`/`sense_citations`/`words.dex_etymon` in `ui.db` (`tools/migrate_ui_db_senses.py`
  back-fills an existing one). `api/word.php` + `detail.php` render the numbered tree with
  collapsible citations, falling back to the flat `definition` for the 41% of the shortlist
  with no Tree/Meaning structure. `bidinea` now ships both senses and all three citations;
  `volintir` (defined only "vezi voluntar") turned out to be the best real-world proof the
  feature was worth building — its sinteză carries a full sense ("Soldat din cetele lui
  Ipsilante…") the flat definition never showed at all. Per-source attribution
  (`MeaningSource`, 924,628 rows) is still deliberately not done — see the idea below.

  **Per-sense synonyms landed the same day, in a second pass** (below `zăticni`'s bug
  report): the first pass dropped every sense whose `internalRep` was empty, which for
  `zăticni` sense `1.` — 9 synonyms, no free text — meant it vanished entirely and the
  surviving sense rendered numbered `2.` with no `1.` above it. `10,798` words now end up
  with a renderable sense/compound/expression, up from `9,177` before the synonym pass.

- [ ] **The DLR/DLRLC citation corpus is structured, not just embedded in prose.** The
  historical-corpus entry under **Bugs** proposes mining dated literary citations out of
  the definition text (`SADOVEANU, P. S. 136.`) as a free in-repo corpus. They do not
  need mining: `Meaning.type = 2` rows *are* those citations, one per row, with the
  attribution intact — 16,843 of them for shortlist words alone, and the full table is
  much larger. `extract_meanings.py` (`docs/senses-plan.md`) extracts them as a side
  effect. Two caveats before treating them as a corpus: they are **selected because they
  attest the headword**, so a raw occurrence count is circular for the word being
  defined — they are evidence for *other* words in the quote; and the attribution is an
  abbreviation (`PAS, L. I 97.`) needing a lookup table to become a date. The senses have
  landed (2026-08-18) — `data/processed/meanings.db` already holds 16,843 citations for
  shortlist words, `type=2`, attribution intact — so the extraction this needed is now
  free; only the two caveats above remain to be costed.

- [x] **Per-sense synonyms, from the `Relation` table.** Done 2026-08-18, same day as the
  entry above, folded into it. `Relation.type = 1` is confirmed to mean "synonym" —
  `zăticni` sense `1.` has 9 `type=1` rows resolving to exactly the 9 words dexonline
  shows under that sense. Landed as a third column on `senses` (`synonyms`,
  pipe-delimited) rather than a separate `sense_relations` table: only `type=1` is read,
  so the extra table the original note considered ("a sense can plausibly have several
  relation types") wasn't needed. Other `Relation.type` values are still unverified and
  unread.

- [ ] **Per-source attribution for senses, from `MeaningSource`.** 924,628 rows, one per
  `(meaningId, sourceId)` pair — could label each sense in the tree with which of the ~100
  dictionaries actually wrote it, the way `sources_meta` already does at the word level via
  `dict_sources.db`. Not needed to render the tree (dexonline's own sinteză doesn't show
  this either), but would let a reader tell a DEX '98 sense from a DLRLC one instead of
  reading them as one merged voice — relevant given how often the entry-tree bleed
  (`docs/senses-plan.md` §7 invariant 3) makes a variant's tree carry its headword's text.

Ranked by impact-per-effort. Effort: XS / S / M / L.

- [ ] **#0 — [S, High] Full Wikisource + CulturaX corpus runs** — `process_wikisource.py` done (14.3M tokens in DB). `process_culturax.py` rewritten 2026-05-12 to use per-parquet-file checkpointing (bypasses `datasets` streaming entirely; no `ds.skip()` cycling bug). Fresh CulturaX run started 2026-05-12; ~40M docs across 64 shards. `validate_diachronic.py` written — computes log2(hist_ppm / modern_ppm) per word, outputs `forgotten_words_diachronic.csv` with verdict (extinct/declining/stable/emerging). Meaningful results require both corpus runs to be complete. See `docs/corpus-options.md`.

- [x] **#0 (old) — wordfreq as primary filter** — tried and found too coarse for Romanian: signal is binary (0.000 or ≥ 3.0, nothing in between). `validate_with_wordfreq.py` remains useful as a rough first pass but cannot replace corpus-based validation. Superseded by Wikisource/CulturaX approach above.

- [x] **#1 — Fix Phase 2 candidate-set mismatch** — fixed in `process_wikisource.py`: loads all ~15k quality DEX forms from `lexemes.db` (frequency > 0.01, description not empty, length > 2) instead of the 1.9k curated CSV. `process_corpus.py` remains unfixed (legacy, low priority).

- [ ] **#2 — [XS, Med] `pyproject.toml` with PEP 621 metadata** — `requirements.txt` exists but no install metadata.

- [x] **#3 — [S, Med] Pick one MySQL→SQLite path; archive the others** — Done. `extract_lexemes.py` is canonical; `convert_to_sqlite.sh` + `mysql_to_sqlite.py` moved to `archive/`.

- [x] **#4 — [XS, Low] Delete `explore_dex.py`** — Deleted. Content was narrative documentation that couldn't run; the useful structural notes are covered by `docs/conceptual-roadmap.md` and `CLAUDE.md`.

- [x] **#5 — [S, Med] Centralize frequency bins in `constants.py`** — Done. Single source of truth for `MIN_FREQUENCY`, `MIN_FORM_LENGTH`, the canonical rarity bins + `rarity_category()` helper, and per-stage candidate ceilings. Canonical `create_curated_list.py` fully driven by it; legacy scripts import their floors/ceilings. Behaviour preserved (boundary-tested).

- [x] **#6 — [M, High] Add lemmatization with `simplemma`** — implemented as a post-classification dedup step in `make_shortlist.py` (2026-05-28). Collapsed 1,571 inflected/derived forms into their canonical lemmas (e.g. `abecedare`→`abecedar`, `murea` removed when alone). Shortlist: 26,788 → 25,217 words. **Remaining gap:** Romanian verb-derived nouns and participial adjectives (`bleui`/`bleuire`/`bleuit`) are not reduced by simplemma and still appear as separate entries. Full corpus-level lemmatization (`bucle`→`buclă` matching) still outstanding.

- [ ] **#7 — [M, High] `tests/` with `pytest` + `ruff` + GitHub Actions CI** — cover normalization and curation heuristics at minimum.

- [ ] **#8 — [S, High] Re-run Phase 2 after fixing #1** — overwrite `docs/phase2-test-results.md` with honest numbers.

- [ ] **#9 — [M, Med] Parallelize tokenization** with `multiprocessing.Pool`.

- [ ] **#10 — [XS, Low] `--yes` flag on `download_wikipedia_ro.py`** — makes it scriptable.

- [ ] **#11 — [S, Med] Calibrate confidence-score weights** — document methodology or at least test sensitivity.

- [ ] **#12 — [M, Med] Filter modern borrowings** — English/French loanwords and brand names inflate false-positive rate.

- [ ] **#13 — [S, Low] Structured logging + `--quiet` flag** — replace decorative banners with levelled output.

- [ ] **#15 — [L, High] Re-run both corpus scripts after load_dex_words() fix**

  `process_culturax.py` and `process_wikisource.py` both had `AND description != ''` in `load_dex_words()`, mirroring the bug fixed in `create_curated_list.py`. Words with empty DEX description but a valid word-class `modelType` (N, F, M, A, VT, VI…) — e.g. `jurnalism`, `ziar`, `lactoză`, `incompetență` — were silently excluded from corpus tracking, so their occurrences were never counted even across 40M CulturaX documents. Both scripts now use the corrected filter (description OR modelType). The corpus DB is stale until both runs complete.

  - **Wikisource re-run**: fast (~minutes on VPS). Wipe `wikisource_ro` rows from `corpus_word_frequency` and `processing_stats`, then `python process_wikisource.py --resume` (checkpoint will be ignored since the word set changed — better to delete `wikisource_checkpoint.json` and run clean).
  - **CulturaX re-run**: long (~hours on VPS). Same procedure: delete `culturax_checkpoint.json`, wipe `culturax_ro` rows, restart. The tracking set grew from ~15k to ~137k words so a full re-scan is necessary.

  Until re-run: `absent` verdict in `forgotten_words_diachronic.csv` conflates "truly unused" with "not tracked by old filter" — results for words with empty DEX description are unreliable.

- [ ] **#14 — [S, Med] Re-evaluate `absent` words for web validation** — after the Phase 1 cutoff was raised to `< 1.0`, the diachronic output now has ~124k `absent` entries (no corpus signal in either Wikisource or CulturaX). Words like `oțios` land here: DEX-canonical but unattested in any corpus. A web validation pass on a filtered `absent` subset (e.g. DEX freq ≥ 0.70, model_type A/N/VT, no loanword markers) could surface genuinely forgotten words that never made it into digitised text.

- [x] **#16 — [M, High] Enrich output CSVs with DEX taxonomy tags** — Done. `Tag` (410 rows), `ObjectTag` (461 k rows), and `EntryLexeme` were already in `lexemes.db`. `create_curated_list.py` now bulk-fetches tags via both join paths (objectType=2 direct, objectType=3 via entry) and writes three new columns to `forgotten_words_curated.csv`:

  - **`dex_register`** (parentId=42 + 17): `învechit`, dialectal, popular, arhaizant, livresc, regional sub-tags (Banat, Moldova, Transilvania…) — 7,642 words covered
  - **`dex_domain`** (parentId=41): botanică, medicină, informatică, chimie, etc. — 3,405 words covered
  - **`dex_etymology`** (parentId=1): limba maghiară, germanism, slavonism, franțuzism, etc. — 35,120 words covered

  Columns flow through `validate_with_wordfreq.py` automatically (DictReader/DictWriter preserves extra fields).

- [x] **#17 — [XS, Med] Flag words with no definition body** — Done. The `has_definition` column already existed in `forgotten_words_diachronic.csv` (and flows into the UI via `validate_diachronic._load_definition_words` → `ui.db.words.has_definition`), and DEX headwords with no extractable definition already land as `has_definition=0` simply by being absent from `definitions.db`. The remaining leak: dexonline's "[Fără definiție.]" placeholder rows (where the entry exists but only usage citations follow) were counted as real definitions. Fixed with `is_placeholder_definition()` in `validate_diachronic.py` — a definition is a placeholder when missing/blank or when "[Fără definiț…" *leads* the text (mid-text occurrences in multi-sense words like *perină*/*spectacul* still count). Mirrored in `ui/app.py` definition load so the UI `has_def` filter and panel text stay consistent (placeholder words still appear, just with no local definition body, linking out to dexonline). Scale in the current `definitions.db`: 7 placeholder-only words (`animaltecă`, `apastop`, `fibrinactiv`, `magnetodiaflux`, `narcorublă`, `perfluorbutilamină`, `relin`). Takes effect on the next `validate_diachronic.py` run / `ui.db` rebuild.

  Note: these words are kept, not dropped — a word documented only as a borrowing with no translation is itself a sign of marginal integration into Romanian.

- [x] **#19 — [XS, Low] Annotation overlay overflow for heavily-annotated words** — Capped at 3 emojis + `+N` superscript in muted mono for the remainder. Template now builds `_ov.items` list instead of string; slices `[:3]` and appends `<span class="ann-more">+N</span>`.

- [x] **#20 — [S, Low] Annotation overlay goes stale after in-panel mutations** — Fixed via HTMX OOB swap: `/bookmark/<word>` and `/tag/<word>/*` routes now re-render the affected `.word-row` partial alongside the detail panel swap so the overlay emoji stays current without a search trigger.

- [ ] **#18 — [L, Med] Extract per-document metadata from corpora for temporal and domain signals** — Currently both corpus scripts discard document-level metadata and only keep aggregate word counts. Two signals worth extracting:

  - **Temporal distribution (CulturaX)**: parquet files carry a `timestamp` field per document. Storing a year histogram per word (e.g. JSON column `year_dist` in `corpus_word_frequency`) would let us answer "when did this word last appear in web text" — a direct measure of *when* usage dropped off, richer than a single `modern_ppm` value. A word with 90% of hits before 2015 and nothing recent is differently forgotten than one that's uniformly rare.
  - **Source domain (CulturaX)**: classify document URLs by type (news, forum, academic, government, blog). A word that survives only in Wikipedia or legal text but never in news or social content is a different kind of relic.
  - **Historical period (Wikisource)**: documents have author/title/century metadata. Words clustering in 19th-century prose vs. spanning multiple centuries give a richer diachronic signal than raw `hist_ppm`.

  **Practical approach** — full reprocessing is expensive. Better: after identifying `extinct`/`declining` words via the current pipeline, run a targeted second-pass scan over CulturaX parquet files for just those ~few thousand words, collecting date and URL metadata. Wikisource period attribution is cheap (12k docs) and could be a side-table join without reprocessing.

  Schema sketch: add `year_dist` (JSON), `domain_dist` (JSON) to `corpus_word_frequency`, or a separate `word_temporal` table keyed on `(word, corpus_name, year)`.


- [x] **#19 — [S, Med] Research UI: browse/filter by more metadata fields** — the filter bar currently exposes verdict, tier, and sort order. Useful additions:

  - **Domain filter** (`dex_domain` column) — already loaded in the `words` table. A `<select>` populated from distinct non-null domain values would let researchers exclude technical jargon (e.g. medicină, drept, informatică) from results, since a domain-specific word being rare in a general corpus is expected, not "forgotten".
  - **Etymology filter** (`dex_etymology`) — filter by language family (slavă, turcă, latină, franceză, engleză, etc.) to answer questions like "are Turkisms more likely to go extinct than Latinisms?"
  - **Register filter** (`dex_register`) — surface all words already tagged `înv.` / `înv` in DEX as a gold-standard archaism set; or exclude them if you want to find words that *aren't* already labelled archaic.
  - **Has definition toggle** — filter to only words with a local definition (definition IS NOT NULL) to avoid clicking through words where the only option is the dexonline link.

  Implementation: each filter is a `<select>` using the same HTMX pattern as the existing verdict/tier dropdowns; `/search` adds a WHERE clause from a safe allowlist. Distinct values for the dropdowns can be computed once at startup from the in-memory `words` table and passed to the template via `g` or a route argument.

- [ ] **#20 — [L, Med] Metadata navigator** — Dedicated tool for browsing the word list by taxonomy and computing metadata statistics. Complements #19 (web UI filters) with deeper analytical access.

  **Statistics view** — aggregate counts and cross-tabulations across the three tag families:
  - Words per register tag (`înv.`: N, `dialectal`: N, …) and per domain tag
  - Etymology breakdown (how many words per source language; which languages contribute most to the "extinct" vs "stable" pools)
  - Co-occurrence matrix: e.g. "how many maghiarisms are also dialectal?", "what fraction of botanică terms are `înv.`?"
  - Frequency distribution (histogram of DEX `frequency` values) within each tag bucket

  **Browse view** — filter and page the curated/diachronic CSV by any combination of tags, with optional sort by verdict or frequency.

  **Implementation sketch** — standalone `browse_metadata.py` reading from any enriched CSV:
  ```
  python browse_metadata.py stats                    # aggregate counts table
  python browse_metadata.py list --register=înv.    # words with that register tag
  python browse_metadata.py cross register etymology # co-occurrence matrix
  ```
  Input: any CSV with `dex_register`, `dex_domain`, `dex_etymology` columns (output of `create_curated_list.py` or `validate_diachronic.py`). See also #19 for web UI filter dropdowns using the same columns.

- [x] **#22 — [S, Med] Hybrid word-marking UX: reserved one-key tags + tag autocomplete** — Done. `i`/`B`/`f`/`x` keydown shortcuts toggle tags via `/tag/<word>/toggle/<tag>`; quick-tags render as a dedicated button row in `tags_row.html` (filtered out of regular pill list); `t` focuses tag input; `<datalist id="tag-suggestions">` backed by `/tags/suggest`; shortcuts modal updated.

- [x] **#21 — [M, Med] Factor in dictionary coverage (how many dictionaries list a term)** — Done. `dict_count` (distinct `sourceId`s per headword) streamed from DEX MySQL dump in `validate_diachronic.py:_load_dict_counts()` (~12s for 301k headwords). Column flows through `make_shortlist.py` → `build_ui_db.py` → UI `words` table; displayed as a `<em>dicts</em>N` chip in `detail.html`.

- [ ] also have a look at [wiktionary](https://ro.wiktionary.org/)

- [ ] go for root semantics fro definitions like _"Acțiunea de a (se) spârcui și rezultatul ei."_



## UI

- [x] make space for columns a bit wider — grid minmax raised to 120px.

- [x] bring superscript count badge closer to word — margin-left 3px → 1px.

- [x] make definition text larger — bumped to 15px; removed inline 11.5px override in detail.html.

- [x] keyboard nav, after focusing on searchbar and filtering words it's hard to get focus back on the term list — Esc from search now restores selectedIdx via selectRow(noClick=true).

- [x] optimize for mobile

- [x] mobile, when scrolling, hide definition drawer. after focus moves on the list

- [x] in info window show which dictionaries this word is found in — `sources` column added to `ui.db` from `dict_sources.db` (98.2% of words matched, exact + diacritic-normalized fallback); rendered as a "📚 N dicționare" chip list in the detail panel. Build: `tools/build_ui_db.py merge_dict_sources()`; one-time backfill: `tools/migrate_ui_db_sources.py`. (Wiktionary membership not yet a data source — separate task.)

- [x] desktop tooltip on hover with definition — floating `#def-tip` div populated from existing `data-def` attribute on `.word-row` via `mouseover`/`mouseout` on the word-list-container. Positioned below the chip (above if near bottom of viewport). No extra network requests.

- [x] top filter, the posibility to remove one attribute - now we can just select. — added an "active filters" chip bar (`#active-filters`) that lists each non-default filter (search, taxonomy selects, ranges, hide toggles, partial verdict/tier/POS groups) with an individual ✕ to clear just that one, plus a "resetează tot". See `renderActiveFilters()` in `app.js`.

- [ ] create statistics by metadata. in the limited corpus and later in whole dexonline

- [x] shareable word viewer url - focus on the word — `?word=<word>` already encoded in URL when panel opens (`syncUrlFromForm`). On page load: panel re-opens via HTMX (`/api/word.php`); after the word list swaps in, `htmx:afterSwap` now also calls `selectRow(idx, true)` to scroll to and highlight the word in the grid.

- [x] hide terms marked as `remove` — hidden by default; "show removed" pill in filter bar re-shows them. ~~**Open question**: what's the semantic difference between `ignore` and `remove`?~~ Resolved: documented as *ignore = not interesting to you (skip)* vs *remove = not a genuinely forgotten word (exclude)*; tooltips added to the quick-tag buttons and the shortcuts modal.

- [x] make .flabel bolder (negative). remove distance between .flabel and choices. Use narrow font for the filter bar — switched to mono 11px bold var(--text-2), removed min-width/excess padding.

- [x] load more words when page scrolled to bottom — replaced "load more" button with HTMX `intersect once` sentinel; auto-loads as you scroll.

- [x] if I click a word with the mouse the focus doesn't move there. Keyboard and mouse choice is not synced — delegated click listener on word-list-container now sets selectedIdx on mouse click.

- [x] longer words break in the info box, make left panel responsive / flexible width — fp-word changed from fixed 170px to auto (min 140px, max 240px).

- [x] mark words that have attached notes or tags/flags. Filter words by tags — dot indicator done; quick-tag filter options (ignore/boring/funny/remove) already in marks select. Custom tags (user-defined via tag input) now also dynamically added to the marks `<select>` via `populateTagFilterOptions()` — called at init and whenever a custom tag is added or deleted.

- [x] select word by typing — type-ahead navigation: unbound printable chars accumulate in a 1.2s buffer, jumping to the first visible word whose normalized text starts with the buffer. Diacritic-insensitive (ț→t etc). Documented in shortcuts modal.

- [ ] search bar also accepts metadata - filters. Later / nice to have enhancement: fancy search, like in gmail with autocomplete and style options. Search box also accepts filtering attributes.

- [x] **Diacritic-insensitive search** — searching `otios` should find `oțios`; `stramosesc` should find `strămoșesc`. Normalize both the query and the indexed word by stripping diacritics before matching (ț→t, ș→s, ă→a, â→a, î→i). Implement in the SQL WHERE clause using a pre-computed `word_normalized` column in the `words` table (populated at build time), or a SQLite custom function. Both PHP and Flask search endpoints need updating.

- [x] **synonyms data** — done 2026-08-08. `scrape_synonyms.py` → `synonyms.db` → `words.synonyms`/`words.antonyms`, rendered as linked chips in the detail panel. The Litera dictionaries (`Sinonime`, `Sinonime82`, `Antonime`) are redacted to 23 characters in `Definition.internalRep`, so `dict_count` knows a word is in them but not what they say. **Corrected 2026-08-14: that is true of the Litera *definition text* only, and was wrongly generalised to "not available from the dump".** The `Relation` table ships in full — 158,860 rows, 164,399 word-level synonym pairs over 63,049 words, ~15s to build, no HTTP. See `docs/sinonime/`.

- [ ] **UI redesign** — fresh-identity, mobile-first redesign spec written for a designer in `docs/design-brief.md` (covers table view, filter-bar redesign, calmer verdict palette, play modes, shared-word landing). Hand off when ready.

- [ ] later show extended definition. everything in dexonline but compact

- [x] exploratory interface. to the point of screensaver. or like tiktok / Tinder feed, but limit per day — shipped as **feed / swipe mode** (`📇 feed` button): one word-card at a time, keep (→ / swipe right → bookmark) or skip (← / swipe left), respects current filters, with a soft daily count (`FEED_DAILY_LIMIT`). Endpoint `api/feed.php`. Further "screensaver"-style auto-advance is a possible enhancement.

- [ ] **Verdict palette saturation review** — four full-saturation colors (red/brown/blue/purple) in the word grid compete equally for attention; consider one dominant verdict color + three muted, or shift to a single-hue density encoding. Out of scope for the 2026-05-18 fine-tuning pass.

- [x] **Bookmark + învechit underline conflict** — switched `.inv .word-text` from `text-decoration: underline dotted` to `border-bottom: 1.5px dotted`. The two indicators now coexist: amber `text-decoration` for bookmark + red dotted `border-bottom` for inv.

- [ ] **Mobile / narrow-viewport breakpoints** — `ui/templates/base.html` has no media queries; the 3-row filter bar and word grid are desktop-only. Add breakpoints for tablet (collapse filter rows into a single overflow menu) and phone (single column word grid, slide-up detail panel from bottom).

- [x] **Filter bar tooltips** — `title` attributes added to all filter bar controls: uitate/rare toggle, verdict pills (with per-verdict explanations), tier pills (with corpus/DEX logic notes), POS pills (full Romanian name as title), sort select, marks select, def toggle, domain/register/etymology/dict_min selects (domain tooltip flags the "any-sense" matching caveat), reset button.

- [ ] **URL-encoded filter state** — encode all active filter values (word_tier, verdict, tier, sort, pos, register, domain, etymology, has_def, marks, q) into the URL query string on every filter change, so that the current view is bookmarkable and shareable. Use `history.replaceState` (no page reload) to update the URL as HTMX triggers fire; parse and restore from `window.location.search` on page load to pre-select the right controls. Both PHP and Flask apps should support this.

- [ ] **Extract inline CSS to `ui/static/app.css`** — `ui/templates/base.html` carries ~870 lines of inline styles. Move to a static stylesheet so it can be cached + edited without touching templates. Set up Flask's static directory if not already wired.

- [ ] do we actually need the word search bar? Does word search add any overhead? Word exploration/discovery should be done by categories, this is not a dictionary. Maybe turn it into attribute search bar. 

- [ ] final list of words, mark some, then pass through llm to filter some more.

- [ ] Meta tags, Open Graph fields, description og image etc

- [ ] web ui: follow schema.org for appropriate entities - add to claude.md maybe?

- [ ] SEO Audit. Including `/llms.txt` 

### joc.php
- [ ] filter out too easy queries - word part/segment that repeats in definition
- [ ] one word can have multiple definitions, include within the choices?
- [x] mark words as unworthy, too simple 
- [x] add bookmarking, favorites, add to list here - by using the game we create an audit tool
- [ ] show definition for failure
- [ ] move game types in the mid of header nav? 
- [x] better emoji for meh - remove

## Misc

- [ ] **DCR export: re-run `scrape_dcr.py --refresh-words` every few months.** DCR3 (2013) is only partially digitized on dexonline.ro — ~183 entries as of 2026-08-17, mostly abbreviations/symbols, and as of that date they carry **no visible definition text anywhere on the site** (no `/sursa/dcr3` wrapper, no meaning-tree badge). The cached `data/processed/dcr3_words.txt` goes stale as new entries land; `--refresh-words` re-enumerates it in 31 requests. Nothing to scrape until the definitions actually render.
- [ ] **DCR (1982, Dimitrescu's first edition) has no digital copy on dexonline.ro.** Only DCR2 (1997) and DCR3 (2013) exist there. If the 1982 word list is ever wanted (e.g. to extend the diachronic window), it needs a source elsewhere.

- [x] create methodology, including activity log, look at activity log and commit history

- [x] tune parameters until it includes `oțios` – maybe use a flag to hide these other, second tier words (new words beyond  current list/limits). What we would also like to surface would be words that are rarely used, but worth attention. The sweet spot might not be totally forgotten words, but let's see which are the rare words but still in use. For the UI we could use a global switch flag. Which corpus to browse, forgotten or rarely used terms?
  - **Resolved (pipeline side)**: `validate_with_wordfreq.py` now emits a `tier` column (`forgotten` / `rare_in_use` / `common`) alongside the existing `is_forgotten` bool. Default thresholds: `--threshold 3.0` (lower, forgotten floor) / `--upper-threshold 4.5` (upper, common cutoff). Rare-in-use words (3.0 ≤ zipf < 4.5) are written to a separate `data/processed/rare_words_wordfreq.csv` so they don't contaminate the forgotten list. Note: `oțios` itself has zero corpus signal (zipf=0.000) so it lands in `forgotten`, not `rare_in_use`.
  - **Still open (UI side)**: add a global switch in the web UI to toggle between the forgotten-words list and the rare-in-use list.

- [x] maybe we should also look in the dictionaries themselves. Are we including really old dictionaries? We could make a page with per dictionary `diff`? Does dexonline dump cover all dictionaries listed here: https://clre.solirom.ro/  https://clre.solirom.ro/content/ro/list-of-lexicographical-works.html https://clre.solirom.ro/content/ro/statistics.html 

- [x] handle in browser curration - choices saved in browser memory and can be exported as json — **partly done**: annotations now sync to `private/app.db` via `api/sync.php`, so curation survives a browser wipe and follows the user across devices on the same account. localStorage remains the offline-first cache. A JSON *export* button is still missing; the data is reachable at `api/sync.php` with `{"since":0}`.

- [x] publish favorites, custom lists even to a web server. make it a collaborative experience. Eventually publish these currated lists and showcase popular words on the main website. — named lists (`api/lists.php`) with a public page at `lista.php?l=<slug>`, plus a streak leaderboard (`api/leaderboard.php`). Identity is an anonymous device token; a display name is requested only when publishing. **Showcasing done 2026-08-07**: `liste.php` carries a *Liste publice* directory — every `is_public` list with at least one word, newest first, with its owner's nickname (`GET api/lists.php?public=1`). Publishing itself moved server-side: `POST {action:'publish_bucket', bucket}` reads the words from the caller's own annotations, so the client no longer uploads the list it is publishing, and `{action:'refresh', id}` re-syncs a published list from its `source_tag` bucket. **Still open**: aggregating which words are most-bookmarked *across* users (a per-word popularity signal, distinct from per-user lists).

- [ ] metadata navigator - add wordfreq and scarcity - the result of this project. 

- [ ] try a super dorpdown navigator, where it can reach all metadata options, witih contextual keyboard shortcuts. or just search by visible terms. but how can we select more or exclude, to make it crazy good? With streer count in brackets?

- [x] **New DEX dump intake** — downloaded `dex-database.sql` (1.65 GB); old dump renamed `dex-database-1.sql` (1.27 GB). Schema is nearly identical (one new index on `Lexeme.pronunciations`). Data growth: Lexeme +3,774, Entry +3,469, ObjectTag +38,074, Meaning +13,367, TreeEntry +5,404; DefinitionSimple unchanged. Four new tables: `Subtitle` (13 M rows — individual Romanian words from 966 YouTube clips, confirmed Digi24 news content, good modern-Romanian corpus candidate), `VideoClip` (966 rows, YouTube IDs), `OCR_stats`, `student`. Actions taken: re-ran `extract_lexemes.py` and `extract_taxonomy.py` against new dump to refresh `lexemes.db`. `validate_diachronic.py` not re-run (waiting for taxonomy join fix above). Subtitle corpus: see #XX backlog entry.

- [x] **definitions.db has severe word→definition misalignment** — `abac` (abacus) is paired with a bacteremia definition; `vânzător` gets a paranasal osteoma definition; `acătarii` has no entry at all despite dexonline showing one. The DB has 83,609 rows so the content is present, but the word↔text association is broken. Likely cause: the extraction script joins on a row offset or integer key that doesn't stably map across tables (e.g. `Lexeme.id` vs `Meaning.entryId` vs `Entry.id` — a multi-hop join gone wrong). Fix: re-examine the extraction query against the DEX MySQL schema; spot-check 10–20 words against dexonline.ro to confirm the join path. Related: the existing `drăngălău` note below.
  - **Resolved**: root cause was a misunderstood schema, not a join error. `DefinitionSimple.lexicon` is the headword (despite the misleading column name), not a dictionary identifier. The old code joined `Lexeme → EntryLexeme → EntryDefinition → DefinitionSimple` and picked the rank-1 definition for each Entry, but Entry records group multiple related-but-distinct words, so the rank-1 definition is often about a *different* word. Fixed by reading `DefinitionSimple.lexicon` directly as the headword key. See commit 8113dbf and `docs/DEFINITIONS_ANALYSIS.md`. Gaps still in the dump are filled by `scrape_definitions.py` (synthesis tab from dexonline.ro).

- [x] **Garbled definitions from DEX dump extraction** — Root cause: `_parse_values` parsed `\n` as the literal letter `n`, leaving dump indentation spaces in the output. Fixed: added full escape table (`\n`, `\r`, `\t`) + `re.sub(r'\s+', ' ')` normalization in `_clean`. Re-ran `extract_definitions.py` + `--merge-only`. Garbled count: 3,152 → 0.

- [x] turn filters from the first row into checkboxes. all selected at first. so we can combine

- [x] create a statistics page. guide yourself by existing filters options. Maybe the statistics page could keep the existing filters - to create dynamic / sliceable statistics?

- [x] **domain taxonomy contains compound nodes with semicolons** — resolved. `_normalize_sep()` in `build_ui_db.py` converts `'; '` → `'|'` before writing `dex_domain` to the DB; the `vocab` table then splits on `|` when counting. Result: `'mineralogie; minerit'` in the raw CSV becomes two separate vocab entries (`mineralogie`, `minerit`) and is filterable individually. Verified in current `ui.db`: no compound strings remain in vocab or in the `dex_domain` column.

- [ ] **domain filter matches on any sub-sense, not primary meaning** — `dex_domain` is set at the word level by aggregating all per-meaning domain tags from DEX. This means a word like *simpatie* (meaning: emotional affinity) appears under medicină because DEX tags one secondary sense as medicină ("legătură între organe simetrice" = sympathetic nerve link); *scaon* appears because DEX tags the compound *scaun rulant* (wheelchair) as medicină; *pipăi* appears for its medical sense of "to palpate". The tags are correct in the source data — this is how DEX models domains. The UI filter is therefore "has at least one medicina meaning" rather than "is primarily a medical word", which can be confusing. Options: (1) show per-word domain count in the word card so the user can judge; (2) add a "strict" domain mode that only matches words whose *only* domain tag is the selected one; (3) document this in a filter tooltip. Related: compound-semicolon entry above.

- [x] definitions have some bugs, `drăngălău` has the `constituent structural al oțelurilor călite și revenite` definition but on the web it doesn't have it https://dexonline.ro/definitie/dr%C3%A2ng%C4%83l%C4%83u/definitii — **resolved** by the same fix as the misalignment item above; `drăngălău` now reads from `scrape_definitions.py` because the DEX dump has no `DefinitionSimple.lexicon='drăngălău'` row.

- [x] see [260515 notes - missing oțios.md](260515 notes - missing oțios.md)

- [x] **[Upstream] Report DefinitionSimple truncation to dexonline developers** — **retracted 2026-08-17, do not file.** The premise was wrong: `EntryDefinition.definitionId` was checked against `DefinitionSimple.id` (61,041 rows, an unrelated small table — plain-text strings with `millShown`/`millGuessed` telemetry columns, apparently the answer key for dexonline's own quiz feature) instead of `Definition.id`, the actual per-source definitions table (`sourceId`, `volume`/`page`, full `@markup@` text). Re-verified directly against the current dump: `EntryDefinition` has 1,379,043 rows referencing 1,186,450 distinct `definitionId`s, and **every single one** resolves in `Definition` (1,231,718 rows) — 0 dangling references, 0.00% gap. The dump is not corrupted. Spot-checked words previously assumed missing (`cfartal`, `mofluzită`) against `Definition` directly: `cfartal` is there as a "vezi cvartal"-style pointer entry, matching the live site; `mofluzită` genuinely has no headword entry of its own (only `mofluz` does) — ordinary dictionary behaviour, not a gap. See the correction at the top of `docs/DEFINITIONS_ANALYSIS.md` and the new item below for the actual fix (extraction was reading the wrong table, not that data is missing upstream).

- [x] **Rebuild `extract_definitions.py` to read `Definition` instead of `DefinitionSimple`** — done 2026-08-17. Added a second pass, `_extract_dex9896_topup()`, that reads `Definition` restricted to sourceId 1 (DEX '98) and 2 (DEX '96) — measurement (see `docs/DEFINITIONS_ANALYSIS.md`) found those are the *only* two of ~100 sources that ship untruncated `internalRep` in this dump, not "the three Litera titles" as CLAUDE.md's synonyms section currently frames it — every other source, including other Academy dictionaries like DEX '84/'75, is truncated to a ~23-char stub. Worth fixing that framing in CLAUDE.md too; flagged, not yet done. `_clean_markup()` renders the internal markup to plain text: `@`/`#`/`$`/`%` are pure typographic wrappers (bold/italic/underline/foreign-cognate) so unwrapping is just deleting the four characters (Romanian prose never uses them literally), `{{...}}` inline editor notes are dropped entirely, `^N` homograph numbers are dropped. The exotic markers speculated about before measuring (`†`, `👉`, `❍`) turned out not to occur in sourceId 1/2 at all — confirmed by scanning all 71,083 rows before writing the cleaner, so the doc above was revised to drop them rather than ship unused-marker handling. Source-priority concern from the original write-up was real but simpler than expected: since the topup only fills gaps `DefinitionSimple` doesn't already cover, and is restricted to sourceId 1/2 from the start, the truncated-source risk never arises — `Definition` is queried with the sourceId check before lexicon/internalRep are even parsed (perf: skips ~94% of rows' text allocation). DEX '98 preferred over DEX '96 on the rare headword collision between the two.

  **Measured impact** (fresh run against the current dump, not the pre-fix estimate): of 18,270 shortlist words, 1,786 had no definition after `DefinitionSimple` + the existing `scrape_definitions.py --merge` checkpoint (most of the historical ~12.8k gap this item originally cited was already closed by scraping since that number was written — it was stale, not the topup's baseline). The topup adds 34,190 new headwords dump-wide (`Definition` sourceId 1/2 minus what `DefinitionSimple` already had) and closes **660 of the 1,786** (37%) — the rest have no untruncated entry under either headword-matching scheme and still need scraping, or (like `mofluzită`) genuinely have no headword entry of their own. `definitions.db`: 70,472 → 92,739 rows. `ui.db` rebuilt; `has_definition=1` now 17,144/18,270 (was 16,484). 17 new tests in `tests/test_extract_definitions.py` (markup cleaner + topup + end-to-end, including that truncated non-DEX-98/96 sources never surface). Full suite: 203 passed. `data/word_ids.tsv` unchanged (git diff empty) — expected, since no words were added or removed from the shortlist, only definitions filled in.

- [x] track synonyms. count synonyms

- [ ] also filter by: masculin, feminin, neutru?

- [ ] Meta: suggest versions, note in both activity log, chronology and readme.

- [x] I also see on dexoline the tag 'rar' but in our interface filters I only see 'învechit' see [săhăstricesc](https://dexonline.ro/definitie/săhăstricesc) — Fixed: `rar` (id=6), `regional` (id=17), `ieșit din uz` (id=239) were root-level DEX tags missed by the `parentId IN (1,41,42)` filter. Extended taxonomy loader to capture them and their children (Banat, Moldova, etc.). `rar`: 2,463 words; `regional`: 3,202; `ieșit din uz`: 95.

- [ ] **Subtitle corpus from new DEX dump** — `Subtitle` table in `dex-database.sql` has 13 M pre-tokenised Romanian word tokens from 966 YouTube clips (Digi24 news). Quick sample: 89k tokens → 11,240 unique types; top words are normal function words. Estimated 1.4% shortlist word coverage in sample (scales to ~20% at full 13M tokens). Too small to replace CulturaX as primary corpus, but valuable as a modern spoken-register spot-check. To use: write `process_subtitles.py` that extracts `SELECT word, COUNT(*) FROM Subtitle GROUP BY word` via `extract_lexemes.parse_mysql_insert` (or a dedicated streaming extractor) and loads into `corpus_frequencies.db` under `corpus_name='subtitle_ro'`. VideoClip table links clipId → YouTube videoId (11-char IDs) if metadata is needed.

- [ ] create presentation video. With Playwright and a scenario, subtitles and generated voiceover. Create youtube account / channel.

- [ ] link to [straturi.mariuscomper.uk](https://straturi.mariuscomper.uk/) / [proiecte/?topic=language](https://mariuscomper.uk/proiecte/?topic=language)

- [x] sharing word lists, can we make them (the url) more compact? compress list of ascii, incl separators? see [gemini](https://share.gemini.google/cHCYz4WpYBrK), [chatgpt](https://chatgpt.com/share/6a746c7a-4150-83ec-96ca-771dc2e47cfa) (both saved under `docs/reference/`) — Done 2026-08-07 via **dictionary indexing**, the option both conversations converge on for a fixed vocabulary. `?words=școală,învățământ,…` became `?w=1.4z.1f2.…`: a version prefix plus one base36 word id per word. Measured 11 chars for 3 words vs 44, 38 vs ~120 for a whole-URL comparison. Neither LZ-string nor gzip was used — with a 25k closed vocabulary, ids beat generic compression and need no library on either side.

  The ids come from `data/word_ids.tsv` (`tools/word_ids.py`), which is **append-only and force-tracked in git** despite the blanket `data/*` ignore. That is the load-bearing part: `ui.db` is deleted and rebuilt on every data refresh, so an id derived from row order would silently repoint every link ever shared. Words are never renumbered and never removed — a word dropped from a later shortlist keeps its id. `build_ui_db.py` assigns ids to new words at the end of a build; `tools/migrate_ui_db_word_ids.py` backfills an already-deployed `ui.db`.

  Codec is `pack_words()` / `unpack_words()` in `api/_lib.php`, exposed to the browser as `api/pack.php` so the client never carries the dictionary. `search.php` accepts `w=` and still honours the old `words=`, so links shared before this keep working. A `w=` that decodes to nothing (mangled, or a future version) yields an empty grid rather than falling through to all 25k words.


- [ ] filter words that appear in only a few dictionaries? – but maybe those words are not interesting as the main scope of the project – we could use a separate db for ancient words?

- [ ] feed, does it hide words in the mainlist? - it should show all tagging options too. and up favorites. down = lol - or show more info?

- [x] top bar, show links to lists (favs, lol, more) fav, the rest are dropdowns if more than 1 — Done 2026-08-07, as a page rather than a dropdown. `📋 liste` in the status bar (and in `joc.php`'s nav, and on `lista.php`) now goes to **`liste.php`**, which lists all four buckets — `fav` / `lol` / `ascunde` / `meh` — with counts, an "open in explorer" link and a publish button each. The `#lists-overlay` modal it replaces was deleted along with ~125 lines of `app.js` and its CSS in `app.css`/`brutal.css`.

  The framing that made this simple: **the buckets *are* the lists.** They are derived from `app.db.annotations` on every request (via the existing `annotated_words_subquery()`), never stored, so they cannot drift. A row in the `lists` table is a *published snapshot* of one — which is why publishing is one button and there is no list-building UI, no per-word "add to list", and no inline list editing.

  - [ ] allow users to submit / post lists - but use captcha? - implement but not activate, as a honeytrap?

  - [ ] then maybe allow users to submit examples of rare words in the wild? - provide gSearch query - then let them submit

- [x] caută un cuvânt - what good is this for? - hide it at least under a magnifying icon

- [ ] make initial view a grid, split by columns? and the table view, also on 2 or 3 colums on desktop?

- [ ] infinte scrolling ok, but update the url bar each say, 100 words, so one can pick up from there - besides the filters?

- [x] mode in each selected words are hidden - for exploration

- [ ] make a list with _*-ațiune_

## Soft-launch
 
- [x] hide diminutive? - filter diminutive at least — `diminutive_like` (403 words) +
  „ascunde diminutive" în panoul explore. Semnal principal: definiția DEX care spune
  „Diminutiv al lui X"; sufixele adaugă 58, dar numai cele neambigue (`-uleț -uliță -ișor
  -ișoară -cioară -uț -uță -șor -șoară`) și numai când baza există în `lexemes.db`.
  - [ ] `-iță` rămâne neacoperit: e la fel de des feminin de agent (*păstoriță*,
    *vorniciță*) cât diminutiv (*clăiță*, *cuconiță*). Ar cere fie o listă manuală, fie
    genul bazei din `lexemes.db` — ~90 de cuvinte în joc.
  - [ ] hide by default
- [x] when showing words lists, filters should be disabled - or 'toate' — un playlist
  (`?w=`) ocolește complet `build_word_filter()` în `search.php`/`random.php`/`feed.php`;
  panoul de filtre devine `inert` și își spune motivul. `q` și `marks` rămân active.
- [x] explain zipf and dex frequency in metodologie — secțiunea 05, `#frecvente`: tabel
  comparativ, scara Zipf și faptul că 16.178 din 16.203 de cuvinte stau la Zipf 0 (sub
  podeaua wordfreq pentru română), deci filtrul Zipf prinde intrușii, nu gradele de uitare.
- [x] optimize UI 'deschide in dexonline', make small, inline with the tags — `.dex-link`
  este acum un chip la capătul rândului de dicționare (`.fp-dicts`), modelat după
  `.dict-chip`, nu un buton plin pe toată lățimea în `.fp-foot`. Toate cele patru skinuri îl
  amplificau independent (beton — placă roșie cu umbră, govuk — buton verde GDS, registru —
  dreptunghi negru cu majuscule mono, tezaur — pastilă plină), deci cel mai zgomotos element
  din panou era un link în afara sitului, înaintea headword-ului și a definiției.
  `.fp-dicts` se randează acum și fără `sources`: altfel linkul ar fi dispărut exact la
  cuvintele cu cea mai slabă acoperire în dicționare. Contrast verificat ≥4.5:1 în 5 skinuri
  × 2 teme (minimul e 4.52, govuk/dark).
- [x] move Statistici & Metodologie in header — **doar pe desktop** (≥901px). Cele două
  intrări se randează în ambele partiale și app.css afișează exact una: header de la 901px în
  sus, footer sub. `top-nav-item--wide` / `nav-item--wide`; nu există lățime la care apar de
  două ori sau deloc. Bara de pe telefon nu duce patru intrări cu etichetă — asta a produs
  împărțirea header/footer din 260809 — dar pe desktop are loc, iar cele două pagini care
  explică proiectul nu-și meritau locul îngropat sub comutatoarele de afișare.
  - Capcană prinsă la verificare, nu la scriere: `.top-nav-item--wide` trebuie declarat
    **după** `.top-nav-item`. Ambele au o singură clasă, deci decide ordinea din fișier —
    declarat înainte, `display:none` pierde tăcut și apar toate patru pe telefon.
- [ ] mobile

  - [x] mobile, make more room for word list when definition is shown — header **și** footer
    se ascund cât timp panoul e deschis (`body.detail-open`, pus în `app.js` la deschidere,
    scos în `closePanel()`; doar blocul ≤768px reacționează, deci o fereastră îngustată pe
    desktop nimerește starea corectă fără resize listener). Panoul rămâne la 60vh, **nu**
    40% cum cerea nota: 40% dintr-un telefon nu încape o definiție (măsurat — `poporanism`
    singur o depășește), iar definiția e lucrul pe care tocmai l-ai deschis. Spațiul vine din
    bare: ~186px dintr-un ecran de 812px, niciuna utilă cât timp citești. Lista vizibilă:
    ~139px → ~325px. Săgeata înapoi înlocuiește ✕ în colțul din stânga sus, țintă de 44px —
    cu headerul ascuns e singura ieșire, deci merge unde o caută degetul.
   See [260810 oțios mobile.jpg](docs/reference/screenshots/260810 oțios mobile.jpg), [260810 oțios mobile 2.jpg](docs/reference/screenshots/260810 oțios mobile 2.jpg)
    - Header compact pe index: **deja era**. Măsurat la 390×844, `.brand-bar` e un singur
      rând de 51px, cu toate cele patru grupuri pe aceeași linie.
    - `joc.php` era însă la 121px: `corecte: 0 · ratate: 0` ocupă 158px dintr-o bară de 362px
      și împingea trofeul pe al treilea rând. Sub 768px scorul se scrie `✓ 0 · ✗ 0`
      (`.joc-score-long` / `.joc-score-short`) → 87px. Plus paddingurile cardului: 28px →
      16px lateral, ceea ce duce lungimea liniei de la 285px la ~325px pe un telefon de
      375px — pentru un card al cărui rost sunt patru definiții de citit și comparat.

  - [x] mobile, search input is always shown — **era deja rezolvat** de mutarea căutării în
    spatele lupei (`openSearch()` / `closeSearchIfEmpty()`). Verificat la 390×844: `#search`
    are `display:none` la încărcare și se deschide doar la click, la `/`, sau dacă URL-ul
    vine cu `q`. Captura din backlog e dintr-un build anterior sau cu o căutare activă.

  - [x] show top nav labels also on mobile - you can instead replace legendă with question
    mark, and remove 'filtre' label - keep the icon — **era un bug de scop, nu o decizie**:
    `.nav-label` e aceeași clasă în ambele bare, iar regula `@media (max-width: 900px) {
    .nav-label { display: none } }` era scrisă pentru `.site-nav` din footer și lua tăcut
    etichetele și din `.top-nav`. Headerul rămânea un rând de emoji goale pe telefon — exact
    ce spune comentariul de deasupra lui `.top-nav-item` că bara de sus există ca să evite.
    Acum e `.site-nav .nav-label`.
    - Loc făcut din cei doi vecini, cum cerea nota: `.shortcuts-alt` („legendă", ~52px) devine
      vizual-ascuns permanent și în schimb `.shortcuts-link kbd` e exceptat de la
      `kbd { display: none }`, deci linkul rămâne capsula `?` de 18px; iar `filtre` e acum
      `<span class="filter-btn-label">`, ascuns sub 768px. Ambele controale își păstrează
      numele accesibil (`title` / `aria-label="Filtre"`), deci nu dispare nimic pentru un
      cititor de ecran — doar pixelii.
    - Bara plătește restul: `.top-nav` gap 14→10px și `.top-nav-item` 0.75→0.6875rem sub 768px.

  - [x] make footer more compact, remove vertical padding — `#status-bar` trece de la
    `5px 16px` la `0 16px` și `.status-right` de la gap 14 la 10px. Cel mai înalt lucru din
    bară e un control `--sm` de 20px, deci paddingul vertical adăuga o treime din înălțimea
    barei degeaba. Paddingul orizontal rămâne: ăla e marginea paginii, nu decor.

  - [x] joc: make it more compact, eliminate unnecessary padding, hide footer, try to make
    header fit in one row. avoid/minimize the necessity of scrolling. — tot ce urmează e
    sub `body.page-ghici` și sub 768px, deci nu atinge nicio altă pagină.
    - **Footerul dispare, iar `--statusbar-h` trebuie să meargă la 0 cu el.** Sunt 76–96px
      cu navigare și comutatoare de afișare, niciunul folosit în timpul unei runde. Dar
      `body { padding-bottom }` și `bottom`-ul panoului citesc tokenul: ascunsă doar bara,
      înălțimea ei rămâne ca spațiu mort la piciorul paginii.
    - **Bara într-un rând.** Măsurat la 390px cerea ~460px: marcă 85 + navigare 134 +
      unelte 225. Diferența de 70px vine din marcă (1.375→1.0625rem), din `brand-tag`, din
      „clasament" de lângă trofeu și — **numai aici** — din etichetele navigării de sus.
      Asta e excepția de la punctul de mai sus care tocmai le-a pus înapoi: un rând de
      glife goale e ilizibil, dar asta e singura bară care duce în plus un comutator de
      mod, un scor și un buton de clasament. Pe orice altă pagină etichetele rămân.
    - Cardul: `.joc-main` 14→8px, `.joc-card` 20/16→14/12px, `.joc-choices` gap 8→6px.
- [x] jocuri
    - [x] rename nav menu idem from 'Joc' to 'Quiz' -> joc.php -> ghici.php — **trei nume
      diferite, intenționat:** eticheta din meniu e `quiz`, URL-ul e `/ghici`, iar cheia din
      `NAV_ITEMS` — pe care o potrivesc `$page` și `aria-current` — e `ghici`.
      `/joc` și `/joc.php` fac 301 către el, în `.htaccess` **și** în `tools/dev-router.php`
      (fără a doua, redenumirea pare că merge local exact până când cineva urmează un link
      vechi în producție). E singurul redirect din fișier și e sigur tocmai din motivul
      pentru care nota de lângă el spune că regula generală nu e: pe `/joc` n-a răspuns
      niciodată vreun endpoint, deci nu există POST pe care browserul să-l facă GET.
    - [x] add url param for each game. ghici?game=sensuri|grila — plus `carduri` pentru
      modul nelistat. **`?game=` e ortografia publică, `mode` rămâne cea internă:**
      `api/quiz.php`, `api/game.php`, `leaderboard.php`, `localStorage['otios.quiz']` și
      statisticile per-mod de pe server continuă să vorbească `sense`/`quiz`/`flash`.
      Redenumite, s-ar re-cheia stare stocată — aceeași categorie de schimbare ca
      redenumirea cookie-ului de device. `?mode=` merge în continuare; a fost singura
      ortografie luni de zile. `replaceState`, nu `pushState`: cele două moduri sunt vederi
      ale aceleiași activități, iar întrebarea nu e niciodată în URL, deci intrările de
      istoric n-ar restaura nimic.
    - [x] hide word definition for 'sensuri' also div.joc-pos and span.fp-pos-line - they
      are spoilers. — `.joc-spoiler` pe toate trei până se decide runda, apoi
      `revealSpoilers()`. Nota avea dreptate că partea de vorbire e problema reală: „s.f."
      sub headword elimină orice variantă formulată ca verb, adică cea mai mare parte a unei
      runde cu patru opțiuni.
      - **Găsit la scriere, nu în notă: o cursă.** `showWordDetail()` e un fetch, deci un
        răspuns rapid poate ateriza cât panoul e încă în zbor — panoul se rezolva *după*
        dezvăluire și re-ascundea definiția exact dezvelită, lăsând „✅ corect!" deasupra
        unui panou gol. De aici `roundDecided`, separat de `answered`: primul înseamnă „s-a
        dat verdictul", al doilea „s-a apăsat o variantă". Fixat în `test_ghici.js` §3.
    - [x] horizontally center joc tools, quiz type selector, points, clasament - top right
      can be ignored on large desktops. — mutate din `$header_tools` în `$header_center`, și
      **asta e ce le centrează**: `$header_tools` aterizează în `.brand-right`, care e
      împins la dreapta de `margin-left: auto`, pe când slotul central e un copil flex care
      poate lua lățimea rămasă. `.landing-tagline` e ascuns pe pagina asta — e celălalt copil
      `flex: 1`, iar doi s-ar centra fiecare în jumătatea lui. Colțul din dreapta sus rămâne
      gol pe desktop lat, cum spunea nota că e acceptabil.
    - [x] sensuri: move tags (fav, lol, meh) above definition for easy accessibility. make
      them larger. — `liftMarks()` mută nodul `.fp-btns` al serverului imediat sub
      `.fp-head`, în loc să-l re-randeze: așa handlerele delegate din `store.js` și
      `hydrateDetail()` merg mai departe neatinse. În ordinea serverului stăteau sub
      definiție, chipuri, sinonime și rândul de dicționare — adică sub un fold, exact pe
      ecranul unde le vrei cel mai des. Mărimea a venit deja din itemul de mai jos (30px
      desktop / 40px telefon); se aplică și aici, e același widget.
    - [x] grilă: add quick actions tagging buttons next to each word (just the icons
      ⭐️,🤣,⛔️) — în `grilă` fiecare variantă *e* un cuvânt, deci toate patru sunt
      marcabile înainte de răspuns: patru cuvinte pe întrebare, cel mai rapid triaj din sit.
      - **Nu refolosesc markupul din `detail.php`, și ăsta e tot rostul.** `#bookmark-btn` și
        `#tags-row` sunt adresate prin *id* în handlerul delegat din `store.js`, deci patru
        copii pe un ecran ar fi patru elemente cu același id și unul răspunzând pentru
        restul. `.joc-mark[data-joc-word][data-joc-tag]`, tratate pe `#joc-card`, cu același
        `getWord`/`updateWord`.
      - **Sunt frați cu butonul-variantă, nu copii.** `.joc-choice` e un `<button>`, iar un
        `<button>` în `<button>` e markup invalid din care parserele își revin aruncând
        butonul interior — deci eșecul arată ca „au dispărut marcajele", nu ca o eroare.
        Fixat în `test_ghici.js` §5.
    - [x] avoid 'meh' words from games — **era deja livrat**, în `api/quiz.php`: atât
      `tag:meh` cât și `tag:ascunde` sunt scoase din `$BASE`, deci și din ținte și din
      distractori. Verificat pe datele reale: user 1 are 192 marcaje meh/ascunde, iar bazinul
      lui scade 16.484 → 16.307 (177 excluse; diferența până la 192 sunt cuvinte care oricum
      nu-s în tierul `forgotten` sau n-au definiție).
    - [x] advance in 1s after correct answer? — **da, dar numai la răspuns corect.** O rundă
      câștigată n-are ce să-ți mai arate pe card; una pierdută e exact invers, cele două
      definiții alăturate sunt tot rostul ei.
      - **Anularea e ce face 1s sigur, nu grăbit.** Orice `pointerdown`/`keydown`/`wheel`/
        `touchstart`, prins în captură pe `document`, oprește cronometrul; la fel apăsarea
        unui marcaj; la fel `load()` însuși, ca un „următoarea" manual să nu lase un
        cronometru pornit în întrebarea următoare și s-o sară. Numărătoarea e o bară care se
        golește pe buton, nu un widget separat: lucrul care numără e lucrul pe care-l apeși
        ca să nu mai aștepți.
    - **Test nou: `tests/test_ghici.js`** — singurul test din repo care cere ceva de pe disc
      (`jsdom`), fiindcă tot comportamentul paginii e comportament de DOM și nu se poate
      verifica pe HTML brut ca la testele de API. Sare curat dacă jsdom lipsește, deci
      `node tests/*.js` merge oriunde. Două lucruri pe care le-a costat corectitudinea:
      jsdom n-are `fetch`, deci fără polyfill pagina se încarcă și pur și simplu nu randează
      niciodată un card; și ramura „răspuns corect" nu se poate atinge la comandă (care
      variantă e bună e secretul serverului, sigilat în `qid`), deci testul joacă runde până
      câștigă una, cu ambele ramuri verificate pe măsură ce apar.
- [x] make tagging buttons a bit larger, both on desktop, but even more on mobile, easy thumb
  targets. — `.qt-btn` 22→30px pe desktop (font 0.625→0.75rem), **40px pe telefon**, la fel
  `#bookmark-btn` (24→30/40px). Erau cel mai mic lucru interactiv din pagină fiind totodată
  cel mai apăsat: marcarea *e* verbul sitului, iar publicarea unei colecții e un buton după
  ea. Pe telefon înălțimea vine din capsulele de tastă, care oricum se ascund acolo — nu e
  nicio tastatură la care să facă aluzie.
- [x] make default / initial theme for new visitors: gov.uk — `DEFAULT_SKIN` în
  `api/_skins.php`, `brutal` → `govuk`. Un vizitator cu un skin deja ales în localStorage nu
  simte nimic; se schimbă doar ce primește cineva care ajunge prima oară.
  - Al doilea loc, ușor de ratat: `despre.html` e static din 260812 și are **o copie de mână**
    a scriptului de boot pre-paint, cu lista de skinuri și defaultul înăuntru. Nesincronizat,
    pagina „despre" ar fi fost singura din sit care se deschide în beton.
- [x] naming: `voroave` – site will be hosted on `voroave.ro` – let's make the necessary
  amendments. — titluri, `og:`/`twitter:` și mărcile vizibile: `stats`, `joc`, `liste`,
  `lista`, `admin`, `despre`, `metodologie`, plus `title=` de pe marca din `header.php`
  (unde scria și „negljate"). Wordmark-ul și `<title>`-ul de pe index erau deja mutate.
  - **Identificatorii interne rămân `otios` și asta e intenționat.** Cookie-ul
    `otios_dev` (`_auth.php:12`) *este* contul — identitatea e un token anonim de device, deci
    redenumit ar da fiecărui vizitator un cont nou și i-ar orfaniza marcajele. La fel cheile
    `otios.theme` / `otios.skin` / `otios.textscale` (preferințele s-ar reseta) și
    `OTIOS_BASE` / `OTIOS_PRIVATE_DIR` / `OTIOS_ADMIN_TOKEN`, care sunt configurație de
    instalare pe server. Redenumirea e strat de suprafață; stratul de stare nu se atinge.
  - **Rămâne o decizie editorială:** `metodologie.html` explica de ce proiectul se numește
    *Oțios* — un paragraf care era despre nume, deci nu putea fi lăsat neatins. Am scris
    varianta minim adevărată (Voroave acum, Oțios înainte, cu povestea lui *oțios* păstrată
    întreagă) și pe cea din timeline am lăsat-o cum era, fiind consemnare istorică. Merită
    recitit de autor.
- [x] center `header.brand-bar span.landing-tagline`. hide on mobile — `flex: 1` +
  `text-align: center`, nu poziționare absolută: centrează în golul lăsat de cele două
  grupuri, ceea ce *citește* ca centrat și — spre deosebire de `absolute` — nu poate ajunge
  sub ele când bara se strânge. E primul lucru care cedează, deci face ellipsis în loc să
  împingă controalele. Ascuns sub 901px, aceeași trecere ca etichetele de navigare.
  - Capcană prinsă la scriere, nu la verificare: `--text-3` e un token de fundal de *pagină*,
    iar `govuk` și `registru` forțează `.brand-bar` neagră în ambele teme — deci textul ar fi
    ieșit aproape-negru pe negru. Re-ancorat în ambele skinuri (`--gv-on-bar-2` /
    `--rg-on-bar-2`), exact lista pe care CLAUDE.md o ține pentru orice locuiește în bara aia.
    Contează mai mult acum: `govuk` e skinul implicit de mai sus.
- [x] theme toggler (.status-prefs .theme-toggle) - only show the available option, hide the
  currently active theme (so always only one icon). Same goes for #view-toggle — un grup de
  două butoane din care unul e permanent aprins cheltuie două glife ca să spună un bit.
  Ascuns cel activ, fiecare devine un buton a cărui față *e* destinația (☾ = „treci pe
  întuneric", ≡ = „arată tabelul"), și footerul câștigă ~26px de fiecare.
  - **Tema se leagă de `:root[data-theme]`, nu de clasa `tg-active`.** Atributul e pus de
    scriptul pre-paint din `_skins.php`; clasa o pune `prefs.js` la load, deci ca regulă
    condusă de JS ambele capsule ar fi clipit înainte să ruleze. Vederea poate folosi clasa,
    fiindcă `#btn-cloud` vine cu `vt-active` chiar din markupul lui `index.php`.
  - **Separatorul `+` a trebuit șters, nu resetat.** `.tg-btn + .tg-btn` se potrivește în
    continuare cu un frate `display:none`, deci supraviețuitorul desena o bordură la stânga
    fără nimic lângă ea — iar resetul nu putea câștiga: `brutal` restatează regula la (0,3,0)
    și încă o dată la (1,3,0) sub `#status-bar`, ambele încărcate după `app.css`. Cu un
    singur buton vizibil per grup separatorul e cod mort, deci a plecat și din `brutal.css`.
    `.scale-btn` și-l păstrează — grupul ăla chiar are două butoane.
- [x] download add to repo external resources, google fonts and htmx. anything else? —
  `assets/lib/htmx-2.0.4.min.js` + `assets/fonts/{app,doc}-fonts.css` și 20 de fișiere woff2
  (796 KB). Zero cereri către terți la încărcarea oricărei pagini.
  - **htmx e verificat, nu doar descărcat:** sha384 al fișierului luat de pe unpkg e
    identic cu `integrity=` care era deja în pagini, deci e bit-cu-bit ce servea CDN-ul.
    Atributele `integrity`/`crossorigin` au plecat odată cu originea străină.
  - **Doar tăieturile `latin` și `latin-ext`.** Acolo stau ă â î ș ț; chirilicul, greaca și
    vietnameza erau greutate moartă pe un sit românesc. Axele variabile s-au păstrat
    (`font-weight: 200 900` la Source Serif 4), deci nu s-a pierdut nicio grosime.
  - **Două foi, nu una:** paginile de aplicație cer Source Serif 4 / Public Sans / IBM Plex
    Mono, `metodologie.html` cere Inter Tight / JetBrains Mono. O foaie comună ar fi pus 130
    KB de Inter Tight pe explorer degeaba. `despre.html` folosește setul de aplicație.
  - **Rămâne extern, deliberat:** `scripts.simpleanalyticscdn.com` (index + metodologie). E
    un tracker prin definiție — auto-găzduit nu mai măsoară nimic. Dacă independența de terți
    e scopul, decizia e să plece de tot, nu să se mute; e o alegere de produs, nu de build.
  - Scriptul care le-a adus: `tools/fetch_fonts.sh` (UA de browser, altfel API-ul css2 dă ttf
    în loc de woff2). De rerulat doar când se schimbă un font.
- [x] select[name="marks"] instead of anotate / neanotate - have marcate / nemarcate —
  etichetele sunt acum `nemarcate` / `marcate` („annotate" era și scris greșit). *Valorile*
  rămân `unmarked`/`marked`: sunt stare de URL, citită de `markedWordsForFilter()`.
  - Găsit pe drum: `marks` era în ambele tablouri de URL din `app.js` dar lipsea din
    `AF_SPECS`, deci filtra grila fără să arate vreun chip — exact golul „înregistrat într-o
    singură direcție" pe care îl numește regula de filtre din CLAUDE.md, pe partea de chip.
  - [ ] Rămâne deschis: un flag care să distingă etichetele publice de cele proprii. E o
    funcționalitate separată și deocamdată nu există nimic public de care să le deosebești.
- [x] After one word is marked, move to next — **la toate patru marcajele**: fav, lol, meh,
  ascunde. Marcarea e o buclă de triaj, iar o buclă în care trei taste te duc mai departe și
  una nu e o buclă la care trebuie să te gândești; un marcaj per cuvânt e interacțiunea
  urmărită, deci posibilitatea de a pune două pe același cuvânt nu merită patru controale cu
  comportamente diferite. (Prima variantă avansa doar la `meh`/`ascunde`, tocmai ca să lase
  fav+lol pe același cuvânt — schimbat deliberat pe 260810: consecvență și comoditate.)
  - **Doar aplicarea avansează, nu și scoaterea.** Un „un-fav" e o corectură, iar avansarea
    te-ar lua exact de pe cuvântul la care tocmai te-ai întors ca să-l repari (verificat).
  - `meh`/`ascunde` scot în plus rândul din grilă — singura diferență între cele două cazuri,
    și tot ce spune al doilea argument al lui `advanceAfterMark()` (`app.js`). La ultimul rând
    se cade înapoi pe cel dinainte, nu se închide panoul; când rândul rămâne pe loc și e
    ultimul, nu se face wrap la început, pentru că asta ar reporni lista pe tăcute.
  - Pentru cazul cu ștergere, rândul următor e reținut *înainte* de animație și regăsit după
    element: rezolvat după ștergere s-ar bate cu animația, iar selectat după index înainte de
    ștergere ar lăsa `selectedIdx` decalat cu unu de îndată ce dispare rândul — și ăsta e
    exact numărul pe care îl citesc j/k.
  - Tagurile personalizate (`#tag-input`) **nu** avansează: le scrii într-un câmp text, iar
    mutarea ar smulge focusul din el.

  - [x] I have changed my mind, also advance on fav / lol - one tag is enough. We preioritize
    convenience and behaviour consistency. — **livrat deja** în `eb11974`: `store.js:161`
    avansează la `fav`, `store.js:187` la `lol`/`meh`/`ascunde`, iar părintele bifat de mai sus
    descrie exact același comportament. Era un copil nebifat sub un părinte bifat care spunea
    același lucru (verificat 260810).
- [x] create 'Despre' page - put in header instead of 'Statistici' & 'Metodologie' which will be linked from 'Despre'. 
- [x] Publish top faves list, hide/demote meh words for everyone else. Use the manual annotations for ordering the list.

  **Livrat 260811.** Obiecția de mai jos n-a fost anulată, ci ocolită prin construcție:
  cele două semnale sunt separate, și **doar unul are voie să scadă**.

  | semnal | sursă | ascunde | reordonează |
  |---|---|---|---|
  | curator | marcajele unui singur user, exportate într-un fișier urmărit în git | ✅ printr-un control vizibil | — |
  | comunitate | marcajele tuturor, agregate live | ❌ niciodată | ✅ |

  Astfel, un vot falsificat cumpără poziție, nu ștergere — exact raționamentul pentru care
  moderarea listelor **nu** are auto-hide după N raportări. Piesele:

  - **`data/editorial.tsv`** (urmărit în git, ca `word_ids.tsv`) ← `tools/export_editorial.py
    --user N` ← `app.db`. Un fișier, nu o citire live, din două motive: build-ul rulează pe
    laptop iar `app.db` e pe server (deci n-au cum să se vadă), și o scădere din vederea
    implicită trebuie să fie un diff cu istoric, nu clickul cuiva. → `words.editor_pick` /
    `editor_demote` prin `tools/build_ui_db.py` sau `tools/migrate_ui_db_editorial.py`.
  - **A cincea clasă „respinse"** (`fără`/`cu`/`doar`), implicit `fără`. O linie în
    `$class_modes` și una în `$CLASS_ROWS`; în `app.js` a fost de ajuns `CLASS_PARAMS`,
    care duce automat parametrul în ambele direcții de URL și în ambele gard-uri de tab.
  - **Sortarea `populare`** = `quality_score + 4·ln(1+voturi)`, rotunjit în benzi
    (`VOTE_BOOST_SQL`, `_lib.php`) fiindcă `LN()` e opțiune de compilare în SQLite. Benzi,
    nu liniar, pentru că seamul `relevant` are 3.495 de cuvinte între 92 și 121: **fiecare
    dublare a numărului de voturi valorează încă vreo două puncte**, deci al 20-lea vot
    aduce ~0,2 unde primul aducea 2,8. Nu e sortarea implicită.
  - **„Alese"** pe `liste.php`, din `ui.db`, fără rând în `lists` — deci există și pe o
    instalare fără niciun utilizator. Fără filtru de seam: 4 din cele 11 alegeri sunt în
    `curiosity`, ceea ce e chiar semnalul că pragul e discutabil.
  - **★** pe rândurile alese (`word_row.php`), în ambele vederi.

  **Măsurat pe datele reale, și e chiar demonstrația:** `barabor` are 20 de voturi ★, toate
  de la conturi-fixture din suita de teste (`tester`, `owner-mod-test`, `pluto`). Cu blendul,
  urcă de la 92 la 104 — mișcare vizibilă, dar rămâne mult sub `văz` (121). `subdialect` ar
  fi ajuns la 124, adică primul, dacă n-ar fi fost marcat `demote` de curator. Adică: exact
  scenariul de sockpuppet a apărut singur, din teste, fără atacator — și l-a ținut în frâu
  amortizarea, nu norocul.

  Rămâne deschis: `--reset-fixtures` în suita de teste (fiecare rulare lasă un user nou în
  `app.db` de dev, iar ei sunt tot semnalul de vot de acolo).

  <details><summary>Obiecția inițială, păstrată pentru context</summary>

  **Amânat deliberat, nu uitat (260810).** Datele nu susțin încă partea a doua. În `app.db`
  sunt 221 de adnotări de la 44 de utilizatori, dintre care 106 de la user 1 (adică de la
  mine), și 41 de `meh` în total. Un „demote pentru toată lumea" construit pe atât înseamnă
  gustul unei singure persoane care rescrie tăcut vederea implicită a tuturor — exact ce
  interzice regula din CLAUDE.md, că nimic nu se scade din vederea implicită fără un comutator
  vizibil, cu un click. E și ieftin de manipulat: identitatea e un token anonim de device,
  deci N „utilizatori" distincți costă N ștergeri de cookie — același raționament pentru care
  moderarea listelor **nu** are auto-hide după N raportări.

  Partea întâi („publish top faves") e ieftină și nu ridică problema asta — `publish_bucket`
  există deja — dar cu 8 favorite de la utilizatorul principal nu are ce publica. De reluat
  când există trafic; e un item post-launch depus înainte de launch.

  </details>
- [ ] also count synonyms! - filter by the number of synonyms?

  **Decis cum, nu încă făcut (260810): se livrează pe date parțiale, dar cinstit.** Acoperirea
  e 2.066 din 16.315 cuvinte, și **zero** în seamul `curiosity` (`synonyms.db` are 2.075 de
  rânduri; ~860 din seamul `relevant` n-au fost încă cerute). Un filtru „număr de sinonime"
  ar arăta `0` pentru 14.249 de cuvinte care n-au fost niciodată verificate — exact capcana
  pe care CLAUDE.md o numește deja pentru `frequency = 0`: lipsa datelor randată ca valoare
  reală. Deci: `syn_count` în `build_ui_db.py`, iar filtrul **exclude** cuvintele nescrapate
  în loc să le numere ca 0, cu eticheta spunând asta. Scrapingul complet (~14.2k cuvinte,
  ~4.5h la podeaua de 1.2s, cu lock pe host) rămâne condiția ca filtrul să însemne ceva pe
  `curiosity`.

  **Deblocat 260814 — condiția de mai sus s-a schimbat mult.** Tabela `Relation` din dump
  acoperă **10.233 din cele 18.270** de cuvinte din `ui.db` (56,0%), față de 2.066 (11,3%)
  de la scraping, și se construiește în ~15s fără nicio cerere HTTP. Cu perechile din
  arborii DEX cu mai multe intrări (`t=5`) urcă la 11.027 (60,4%), iar cu scrapingul
  existent la **11.517 (63,0%)** — inclusiv în seamul `curiosity`, unde până acum era zero.
  Deci `syn_count` se poate calcula pe date reale acum, iar regula „exclude în loc să
  numeri 0" rămâne validă exact pentru cele **6.753** de cuvinte rămase neacoperite.
  Vezi `docs/sinonime/`.

- [ ] **sinonime: revizuiește ~50 de perechi `t=5` (co-apartenență la același arbore DEX)**

  Blocantul dinaintea afișării lor. Aduc 38.321 de perechi și dau primul sinonim pentru
  25.554 de cuvinte (+5,4 puncte pe banda 1k+), dar eșantionul e amestecat — `pârpolatic`,
  `astatic`, `îhî`, `părtie` — fiindcă tovarășii de arbore sunt uneori variante grafice, nu
  sinonime. E o judecată despre limbă, nu o măsurătoare. `ui.md` le ține stocate și
  neafișate și le rezervă tratamentul vizual (muchie punctată în `--syn-tree`, sub type-1,
  etichetate „din același cuib DEX"); tratamentul pregătit **nu** e permisiunea de a le
  aprinde. `escalate.md` §6.

- [x] **sinonime: re-măsoară dimensiunea lui `syn.db` după `edge.rank`** — măsurat 2026-08-17.

  Cifra de ~10–11 MB din `findings.md` §8 a fost măsurată pe DDL-ul *fără* coloana `rank`,
  fără `merge_scrape()`, fără type-5 — adăugate ulterior de `spec.md`'s build rules 6-7.
  Construită literal (simetrizare ca al doilea pas de scriere, `sense_word` = SW ∪ TW),
  baza a ieșit la **21–23 MB**, peste plafonul de 16 MB. Simetrizarea mutată la interogare
  (`lookup_related()` unește sensul direct cu cel invers, în loc să dubleze rândurile la
  construcție) a adus-o la **15,6 MB** — sub plafon, cu `sense_word`/`edge` exact cum le
  descrie schema (o singură direcție pe rând). Vezi `tools/build_syn_db.py`'s
  `build_relation_graph()` pentru explicația completă.

- [ ] **sinonime: exemplul de "empty state" din `ui.md` (`celșag`) nu mai e gol**

  `ui.md`'s landing/empty-state copy numește `celșag` ca exemplu de cuvânt fără sinonime —
  adevărat față de graful `Relation` singur (`findings.md` §6 îl listează explicit printre
  cele 524 de cuvinte doar-scrapate, absente din `Relation`), fals după ce scrapingul e
  contopit: `celșag` chiar înseamnă „înșelăciune" și are 11 sinonime scrapate (`amăgire,
  înșelare, înșelăciune, ...`). `tests/test_sinonime.js` folosește `acardiac` în loc
  (cuvânt real, zero muchii). Dacă `ui.md` e revizuit, exemplul din text ar trebui înlocuit.

- [ ] **sinonime: trecere prin cele 6 skin-uri × 2 teme, cu screenshot-uri**

  Construit 2026-08-17, verificat doar programatic (noduri, texte, structura HTML) și cu
  token-urile `--syn-node`/`--syn-edge`/`--syn-ant`/`--syn-tree` declarate o singură dată pe
  `:root` (moștenesc tema automat prin indirecție `var()`, fără redeclarare în blocul dark).
  Nu s-a făcut trecerea vizuală cu screenshot-uri pe care `ui.md` § Skins o cere explicit —
  în special `govuk` (`--radius: 0`, masthead negru) și `registru` (`--accent` e cerneala
  paginii, deci orice umplut cu `--accent` într-o zonă întunecată dispare, ca bug-ul
  `.joc-mode.active`). Verifică și starea `.is-active` la (0,3,0) în toate cele 6.

- [ ] ascunde cuvinte care au în definiție 'vezi ...' + alt cuvânt care suna f similar?
- [x] another data quality run? – use more input sources?

  Prea vag ca să fie un task: e un proiect. Reclamațiile concrete există deja, scrise, în
  secțiunea **260519 Data Audit** de mai jos (definiții lipsă la formele feminine, grafii
  variante care poluează explorarea, `fost` / `văr` / `nepot`). De spart în verificări cu
  nume, plecând de acolo — nu e un blocant de soft-launch în forma asta.
- [x] use other corpuses? [romanian-nlp-datasets](https://github.com/AndyTheFactory/romanian-nlp-datasets), [LUMRO](https://github.com/upb-nlp/LUMRO), [RELATE](https://relate.racai.ro/) - Romanian Portal of Language Technologies, [Romanian text corpora](https://www.sketchengine.eu/corpora-and-languages/romanian-text-corpora/), [A Culturally-Rich Romanian NLP Dataset from "Who Wants to Be a Millionaire?" Videos](https://arxiv.org/html/2506.05991), [Statistics of a Large-Scale Romanian Corpus for Language Modelling](https://rjp.nipne.ro/2025_70_7-8/RomJPhys.70.111.pdf), [Resources and Tools for Computational Linguistics](https://nlp.unibuc.ro/resources.html), [Natural Language Processing Tools for Romanian – Going Beyond a Low-Resource Language](https://ixdea.org/wp-content/uploads/IxDEA_art/60/60_SP_1.pdf) etc?
  
  - [ ] see: [260810 Grok - extend corpuses analysis](/docs/reference/260810%20Grok%20-%20extend%20corpuses%20analysis.md), [Gemini - Romanian NLP Corpora and Tools](docs/reference/260810%20Gemini%20-%20Romanian%20NLP%20Corpora%20and%20Tools.md)

  - **Răspunsul verificat: [`docs/corpus-expansion-plan.md`](corpus-expansion-plan.md)** (260810).
    Cele două rapoarte de mai sus sunt utile dar neverificate — ambele descriu greșit ce face
    pipeline-ul, iar Gemini recomandă exact comparația în ppm care e gotcha #1 din `CLAUDE.md`.
    Planul e ordonat după dovezi câștigate per efort; primele trei puncte nu cer niciun corpus nou:

    - [x] **1. `hist_docs` în `aggregate_by_family`** (S) — **rezolvat 260810**, vezi item separat mai jos.
    - [x] **2. `subtitle_occ`** — **investigat 260810, recomandarea retrasă.** `subtitle_ro`
      nu poate fi semnal de uz modern: ~1/6 din corpus e televiziune de muzică populară.
      Cuvintele cel mai supra-reprezentate față de CulturaX nu sunt de știri, ci de cântec
      (`țurai` 119×, `mândruliță` 242×, `neicuță` 122×, `lai` 332×), iar reconstruind clipurile
      din tabelul `Subtitle` (are `clipId`) toate cele 7 verificate sunt emisiuni de folclor —
      două sunt versuri transcrise, nu vorbire. Clipurile cu ≥3 markeri de gen: **15,6% din
      tokeni dar 27,5% din ocurențele cuvintelor din shortlist**, iar **444 din 2.446 de
      cuvinte atestate apar *numai* acolo**. A pune asta în `verdict()` ar fi salvat exact
      cuvintele pe care proiectul le caută. Defectele de plumbing sunt reale, dar nimeni nu
      citește `subtitle_ppm` (nici PHP, nici JS), deci nu se repară un semnal care nu trebuie
      folosit. Două ieșiri, ambele decizii: filtrează clipurile de folclor și re-rulează
      `process_subtitles.py` (~11M tokeni de știri reale), sau inversează-l într-un flag de
      registru „cântec tradițional", lângă `regional_only`.
    - [x] **3. Liste de frecvențe CoRoLa** — **încărcate 260810, dar neconectate deliberat.**
      `process_corola.py` → tabelul `corola_lemma_frequency` (1.457.518 leme, 665,9M tokeni,
      0 rânduri malformate). Licența: proiectul e necomercial și nu redistribuie nimic, deci
      se folosește **doar ca intrare** — niciun număr derivat din CoRoLa în `ui.db`.
      - [x] **Problema lemelor: rezolvată 260811, dar nu cu un algoritm.** Arhiva conține și
        liste de **forme de suprafață** (`corola_word_freq_*`), care respectă invariantul lui
        `corpus_word_frequency`, deci `aggregate_by_family` face rollup-ul cu paradigmele DEX
        și cu împărțirea după prominență. `strugur` și `strugure` chiar împart
        `struguri`/`strugurii`/`strugurilor` — exact cazul `veșcă`/`veste`. Rezultat:
        `strugur` 12.176 → **749**, `strugure` 724 → **12.034**; `gherghină` 3.658 → 63;
        `cadră` 51.181 → 103. `process_corola.py` încarcă acum lista de cuvinte și șterge
        tabelul de leme. **Nu reintroduce listele de leme.**
      - [ ] **Blocantul real: CoRoLa acoperă 1945–prezent**, deci nu e un corpus „modern" în
        sensul proiectului. Conectat la `modern_occ` pentru exact un build, apoi retras:
        față de CulturaX, `condițiune` 112,8×, `comisiune` 49,6×, `dorobanț` 41,1×,
        `iscăli` 15,7× — primele două sunt grafii dinainte de reforma din 1953, pe care un
        corpus care începe în 1945 le conține inevitabil. Efect: 686 de cuvinte scoase din
        shortlist și **35 din seamul `relevant`** — `birjă`, `dorobanț`, `vechil`, `dijmă`,
        `cocoană`, `iscăli`. Adică exact materialul cel mai bun al proiectului, dispărut din
        vederea implicită fiindcă apare în literatura de la mijlocul secolului.
        Căderile erau semnal real, nu aritmetică (contribuția mediană CoRoLa 37,7% față de
        3,8% creștere de panel; cei mai mari câștigători, nominalizări juridice —
        `rămânere`, `ajungere`, `discutare`, `analizare`). Doar că înseamnă „viu în optzeci
        de ani de română publicată", nu „viu acum".
        **De făcut**: un *al treilea* panel cu înțelesul lui („atestat în corpusul de
        referință") plus tratament `specialist_alive` pentru registrul juridic — nu un
        termen adăugat la panelul modern. Listele n-au date, deci o felie post-2000 nu se
        poate lua din sursa asta.
    - [x] **4. LUMRO** — **ingerat 260810** (`process_lumro.py`, în `HIST_CORPORA`).
      175 romane, **5,07M tokeni** cu tokenizatorul pipeline-ului (nu 7,52M — ăla era dintr-un
      regex mai larg), 111 autori, 1845–1920. Efect: **381 de cuvinte trec pragul de atestare**
      (toate `absent` înainte), **509 promovate `curiosity` → `relevant`, zero retrogradate**,
      shortlist 16.557 → 17.594. Predicția anterioară de 1.327 era față de shortlist-ul de
      *dinaintea* reparării `hist_docs`, care salvase deja majoritatea acelorași cuvinte.
      - [x] **Autorul e folosit: `document_count` = autori distincți, nu romane** (260810).
        `hist_docs >= 2` e o afirmație despre *independență*, iar trei romane ale aceluiași
        romancier sunt vocabularul unui singur om. Măsurat înainte: din 1.425 de cuvinte a
        căror atestare o dă LUMRO, **638 (44,8%) veneau de la un singur autor** —
        `jupâneșică` cu 47 de ocurențe, toate V.A. Urechia. Ocurențele se adună în
        continuare peste toate romanele; se corectează doar independența.
        **Efectul real e mic și merită notat**: doar **315 cuvinte** apar în mai multe romane
        ale aceluiași autor, deci doar atâtea pot fi mișcate — 10 verdicte schimbate, 3 ieșite
        din seamul `relevant`, 17 din shortlist. Principiul contează mai mult decât cifra.
        Fixat de `tests/test_process_lumro.py`, fiindcă „numără romane" e simplificarea
        evidentă. Wikisource numără în continuare pagini: n-are metadate de autor.
      - [ ] Rămâne nefolosit: **anul**. Ar face posibile curbele pe decenii (1840–1920, deja
        parsate la fiecare rulare). E o decizie de schemă plus un consumator în UI — nu se
        construiește până nu există ce să le citească.
    - [ ] **5. Metadate CulturaX** (L, amânat) — `process_culturax.py` nu păstrează
      `timestamp`/`url`/`source`. Ar separa dovada din 2013 de cea din 2023 și sutele de
      gazde independente de o pagină de dicționar oglindită — dar cere reprocesarea a 40,3M
      documente. De făcut după 1–4.

    Nerecomandate acum: FuLG / OSCAR / CC-100 (tot Common Crawl, nu un eșantion independent);
    MARCELL și corpusuri de domeniu (utile ca *control* care produce `specialist_alive`, nu ca
    dovadă generală); datasetul „Who Wants to Be a Millionaire?" (prea mic pentru frecvențe).
- [x] **`hist_docs` e 0 pentru lemele care nu domină nicio formă** (găsit și rezolvat 260810,
  defect anterior). În `aggregate_by_family` (`validate_diachronic.py:376-388`) ocurențele se împart
  proporțional între pretendenți, dar documentele sunt totul-sau-nimic: `if share >=
  DOMINANT_SHARE` (0,5). O lemă care nu e niciodată pretendentul majoritar al *niciuneia*
  dintre formele ei adună ocurențe și exact zero documente. Apoi `verdict()` cere
  `hist_occ >= 3 AND hist_docs >= 2`, deci jumătatea „docs" o anulează pe cea „occ".

  Măsurat pe shortlist: **5.780 rânduri (35,7%) au `hist_docs == 0`, dintre care 170 au
  `hist_occ >= 3`** — atestate după propriul prag de ocurențe, dar forțate la `absent`.
  `soli` (occ 132, share 0,418), `nalt` (occ 98, share 0,223) și `văz` (occ 96, share 0,108)
  sunt toate în seam-ul **relevant**, deci se văd în vizualizarea implicită.

  Aritmetica ocurențelor e corectă (0,108 × 888 = 96 ✓); doar documentele sunt problema.

  **Rezolvat**: documentele se scalează acum cu același share ca ocurențele (`d * share`),
  păstrând `max` peste forme în loc de sumă. `DOMINANT_SHARE` a dispărut. După rescore:
  `hist_docs == 0 & hist_occ >= 3` a trecut de la **170 la 0**; 189 verdicte schimbate
  (185 `absent` → `historical_only`); 77 cuvinte promovate `curiosity` → `relevant`.
  `văz` primește 42 documente (392 × 0,108), `soli` 62, `nalt` 67.

  Două cuvinte au mers invers — `arestui` și `barbetă`, docs 2→1 la `hist_occ` 3 — pentru că
  erau exact pe pragul de zgomot și scalarea proporțională taie în ambele sensuri. E
  comportamentul corect, nu un defect nou.
- [x] explain how to use the site, how it works, how tagging / lists work.
- [x] **Investigation consolidated into F07; fixture repair remains open there.**
  Reproduced 2026-10-05: both hardcoded words are absent from the audited UI database.
  This explains a zero watermark and the later JSON parse failure. It is separate from F02's queue race.
  **Historical report: `tests/test_store_sync.js` pică la „sync watermark stored"** (observat 260810, nu
  introdus atunci — reprodus și cu `store.js` din HEAD, deci e anterior). Verificarea e
  `!!JSON.parse(ls['otios.sync']).since`, deci un `since` întors ca `0` sau lipsă o pică, iar
  pasul următor moare pe `JSON.parse(undefined)`. De văzut dacă e starea `app.db` de dev sau
  chiar `api/sync.php`. Celelalte trei suite JS trec.
- [x] quizz/ghici.php sensuri still shows diminutive. sfințișor - diminutiv al lui sfânt —
  **Fixed 260812.** `is_pointer_sense()` in `api/quiz.php` now rejects „Diminutiv/Augmentativ
  al lui X" the way it already rejected „vezi X". `reveals_word()` was supposed to catch it
  and could not: it needs a 4-character shared prefix and Romanian vowel alternation breaks
  that at character 2 (`sfințișor`/`sfânt` share „sf"). 385 first segments in the pool were
  one of these; 305 of those words have another usable sense and stay. Same pass: `dex_variant`
  and `archaic_spelling` words are excluded from the quiz outright (867 rows) — their
  definition is their headword's, so `sofragerie` was asking the player to produce a dead
  spelling from a living word's definition with the real answer among the distractors.
  Pinned by §5 of `tests/test_game_api.js`.
- [x] info / definition box, even on desktop move it to the bottom - as on low res, but make it not full width, with some transparent margin to the sides, horizontally centered. so it's closer to the eyes. maybe even a tiny bit / soft shadow. —
  **Done 260812.** `#detail-panel` is the bottom sheet at every width now, capped at
  `min(60rem, …)` and centred, with `--panel-shadow` as a token in both theme blocks.
  Centred on the *list*, not the window — the docked rail is 288px, so viewport-centring
  tucked the headword underneath it; `--rail-w` is subtracted from both the offset and the
  width. `scroll-padding-bottom` keeps the last rows and `j`/`k` clear of the overlay.
  `brutal` and `registru` had rules written for the old right-hand column and both were
  wrong as a card; fixed. See **The definition panel** in CLAUDE.md.
- [ ] word sharer. 
  - [x] update .htaccess, turn `/?word={word}`  to `/def/{word}` — decided: **word slug,
    dexonline-style, not `word_id`.** Safe as a rewrite for the reason `/joc → /ghici`
    was — no API endpoint answers under that prefix. Must be **additive**: `?word=` links
    keep resolving, with `rel=canonical` naming which spelling counts (despre/metodologie
    already do this). Note ~40% of headwords carry diacritics and percent-encode
    (`/def/%C8%9Beara`), so the pretty URL is only pretty for the rest.
  - [x] close the filter drawer
  - [x] add dynamic meta, title, description, og info — **Done 260812.** `share_meta()` in
    `api/_lib.php`; see **Share metadata for `?word=`** in CLAUDE.md. Done before the URL
    change on purpose: it needs no new URL, so it fixes every link already shared rather
    than only future ones. Pinned by `tests/test_share_meta.js`.
  - [ ] later: could we show related words? or just top public favorite and loled words – though they shouldn't repeat too often, add  randomness factor?
    Note: this is a *display* of community marks, not a filter, so it stays on the right
    side of the rule that votes may only ever reorder — see `vote_counts_subquery()`.
- [ ] maybe split _meh_ into _comun_ & _irelevant_?
- [ ] also demote words that have a single word definition? if it sounds familiar. or just give them to me in a sharable list first

- [ ] in og:description reverse order, start with term definition, _then_ category.
- [x] start with light theme?

### Next
- [ ] filters: add dictionaries (w published year)
- [x] register_tags_shortlist more tags that we have in filters - use them! —
  **Done 2026-08-18.** The `registru` filter dropdown only listed 17 of 51 distinct
  `dex_register` values; `build_ui_db.py` excluded 34 usage-style tags (`figurat`,
  `popular`, `argou`, `vulgar`, ...) via `_REGISTER_USAGE_NOTES`, on the theory that they
  describe rhetorical style rather than archaic/rare status. The info box already showed
  all of them unfiltered (`detail.php` reads raw `dex_register`, no exclusion) — only the
  filter dropdown was narrower than the data. Removed the exclusion; the vocab-population
  loop is now `build_vocab_table()` in `build_ui_db.py`, callable per-kind so
  `tools/migrate_ui_db_register_vocab.py` could backfill the existing `ui.db` without a
  full rebuild. No query-side change needed — `build_word_filter()`'s LIKE match already
  covered any `dex_register` value.

  **Follow-up, same day:** each register option now shows its word count in brackets
  (`vocab_counts()` in `_lib.php`, used only by `index.php`'s register select) — a static
  global count, not recalculated per filter selection. Live per-selection counts were
  asked about and declined: `facet_counts()`/`applyFacetCounts()` already did this once
  (2026-08-11) and were reverted the next day for being wired to only a handful of
  boolean toggles (never the taxonomy dropdowns) and for costing a row via wrapping — see
  **"There are no per-option counts"** above. Redoing it now, for register alone, would
  repeat exactly the piecemeal pattern that got it cut. If live counts come back, it's
  still all groups or none, wrapping solved first.
- [ ] are we properly citing sources? corola, lumro etc?
- [ ] Colecții viewer atât compact cât și cu detalii / meta, să vedem ce nu ne place 
- [ ] explorer power user mode, shift + arrow marks as fav/meh/lol. 
  - [ ] smart search input, including gmail like search parameters
- [x] check consistency, when a word is tagged by myself the tag is activated in the info box
- [ ] build an even more straightforward quick tagging UI? annotation optimized ui.
- [ ] add straturi as per [straturi.mariuscomper.uk](https://straturi.mariuscomper.uk/)
- [ ] rescriu metodologie după înțelegerea mea – then create a llm/human version tool, that shows the selected version in context - same page section
- [ ] add contact, gform sau tally.so 
- [x] can I git pull/sync just the `/public/` subfolder? 
- [ ] why don't se use the same set of filters pentru stats?
- [ ] definition box - add a tint of background, for contrast. 
- [ ] add interstitials
- [ ] check [surse](https://dexonline.ro/surse) and [dexonline wiki](https://wiki.dexonline.ro/)
  - [ ] scrape [DC3](https://solirom-clre.gitlab.io/texts/dcr3/site/)
- [ ] to manually revisit words that are "vezi și... " the 8: https://voroave.ro/?w=1.1f7.jkz.29y.4q6.509.5fq.66a.8da all 68: https://voroave.ro/?w=1.1f7.jkz.29y.4q6.509.5fq.66a.8da.14.3o.dx.jv.15w.17n.181.1en.1et.1f0.1f1.1f9.1fa.1fy.1gu.1gx.1h1.1i8.1iy.277.29w.2yc.4fk.5jx.84e.84u.856.juc.8by.8lj.8us.8v0.9i7.a1n.a1v.aal.bkq.bod.boo.bv3.bw3.c3p.efa.evl.eyb.k6e.h35.h37.h38.h39.h4a.hf9.hiq.hs3.hu1.huq.hvi.i6u.ii6.j6s
- [ ] we're not showing the full definitions. should we scrape the others/initial too?
- [ ] word definitions, sometimes we're showing the secondary definition, see `zăticni`
- [ ] ux: wordlist should be the next tabindex after search box (when showing results)
- [ ] are we ignoring DCRs? we should be
- [ ] check [lexicro.com](https://api.lexicro.com/docs)
- [ ] noticed DEXonline definitions have a json/xml feed, `https://dexonline.ro/definitie/{cuvânt}/{json|xml}`. Found out about it on [dexonline/issues/562](https://github.com/dexonline/dexonline/issues/562). See also [balajmarius/dexonline-mcp-server](https://github.com/balajmarius/dexonline-mcp-server)

## Post launch

- [ ] extra: DCR explorer – see how words appeared and drifted. anything from DCR made it to any other dict?
- [ ] REBUS pentru masochiști
- [ ] traffic analytics
- [ ] SEO webmasters registrations
- [ ] write scientific paper(s). 1. method, 2. conclusions – co-publish with academic?
- [ ] write articles, scena9 or such
- [ ] romo video: explain very fast in robot voice everything we did. cât de ușor e treaba cu un robot. metodologie într-un minut. turuială. facem șî versuri, hip-hop?

### Extend

- [x] quizzes — multiple-choice quiz (definition → pick the word, 4 same-POS choices, target word masked in the prompt) on `joc.php`, with streak/record in localStorage. Endpoint `api/quiz.php`.
- [x] flash cards — word → reveal definition card on `joc.php` (shares `api/quiz.php`), with "păstrează" to bookmark. Button removed from the mode bar 2026-08-01; still reachable at `joc.php?mode=flash`.
- [x] sensuri — reverse quiz (word → pick among 4 definitions) on `joc.php`, now the default mode. `api/quiz.php` returns an `options[]` array of `{word, definition}`; definitions are cleaned server-side (first segment before `|`, ≤200 chars) and low-quality entries are filtered out of the pool.
- [ ] fomfleuri: create **eye movement** following word tagging UI. Sau Minority Report-like UI [gesture-synth](https://indecisiveeric.com/gesture-synth)

## 260519 Data Audit

- [ ] some terms still lack definitions, although they are present (the definitions) on dexonline. Ex: 
  - `mofluzită`, `libovnică`, `ischiuzară`, `consumatoare` - so _genul feminin_, feminine versions of words.
  - `cfartal` - is a different spelling of `cvartal` – dexonline has the url (https://dexonline.ro/definitie/cfartal), but the word in dexonline is `cvartal`. Same with `prijuni` --> `sprijini' (https://dexonline.ro/definitie/prijuni)
  -  `murea` (form of `a muri`), `abecedare` (plural of `abecedar`)
  - other examples: `ospătător`, `săhăstricesc`, `bașfir`, `aeresc`, `gad`, `pestitor` 
  - analyze and figure out the cases where definitions are missing – even after our initial dexonline scraping attempt.  
  - do these also mess with our statistics?
  - differently spelled variations shouldn't be listed, it poisons word exploration - or listed separately?

- [ ] why does the list contain `fost` -- this is a form of a very popular verb, `a fi`? See also other common words: `eleșteu`, `văr`, `nepot`, `coproducție`
  - **Partially resolved**: `fost` and `coproducție` removed by the `modern_ppm > 5.0` Tier A guard (2026-05-28). `eleșteu` is correct — it's a genuine archaic word (fishpond, modern_ppm=0.055). `văr` (1.4 ppm) and `nepot` (3.1 ppm) remain as borderline cases; their inflected nature would be addressed by lemmatization (backlog #6).

- [x] cuvinte rare has waay too many common words: manipulat, mediere, adițională, agravat, neurologie, organizatoare, cowboy, spitalizare – but still **not** `oțios`?!
  - **Resolved**: `validate_with_wordfreq.py` now gates `rare_in_use` on non-empty `dex_register` — words with Zipf 3.0–4.5 but no register tag fall to `common`. Rare list: 11,668 → 469. `oțios` addressed by Tier C in `make_shortlist.py` (`dex_absent_highfreq`, threshold dex_frequency ≥ 0.85); now appears in UI.

- [ ] all forms of terms listed, ex: `bleuit`, `bleuire`, `bleui` – could we just show one entry (as a bundle)? Also `blehui`, `blehuire`, `blehuit` – root word, `bleau`. IF root word not in list we should also remove references? Most words in rare --> filter --> popular. 

- [x] `cimbru` appears at `rare` / filter: `în comparații / la comparativ`. — **Fixed**: `în comparații / la comparativ` removed from register filter dropdown via `_REGISTER_USAGE_NOTES` exclusion set (2026-05-28). `cimbru` itself correctly stays in `rare_in_use`.

- [x] `uitate` / filter: `în comparații / la comparativ` - words that don't seem to have anything with comparații -- can you backtrack on how did that end-up there? — **Fixed**: `în comparații / la comparativ` is a DEX usage-context note (word can be used in comparative phrases), not an archaic register. Removed from register filter dropdown via `_REGISTER_USAGE_NOTES` (2026-05-28). 38 other usage-style tags cleaned up at the same time.

- [ ] rare / Filter: `Maramureș` lists 'biodiversitate'

- [ ] remove _diminutive_, maybe?

- [ ] how come psihoanaliză be a dex 4

- [ ] remove old spellings, `giudecător` – can we check pronountiation - if it's too close to a popular word, flag it for removal

- [ ] sort reverse 

### UI follow-ups (2026-08-01)

- [ ] 🎲 "la întâmplare" — hidden in the brand bar pending a manual-selection design (pick from the current filter set rather than pure random). `surpriseWord()` + `r` shortcut still live; unhide the button in `index.php` when the design lands.

- [x] Cmd/Ctrl+R hijacked by the `r` shortcut — global keydown handlers now ignore events carrying meta/ctrl/alt (`app.js`, `joc.php`).

- [ ] Note textarea: Enter saves, so Shift+Enter can't insert a newline (`app.js` capture-phase handler on `#note-input`). Decide whether multi-line notes matter; if so, save on Cmd/Ctrl+Enter or blur instead.


## Server-side accounts — follow-ups (2026-08-02)

- [ ] **Account recovery — decision tracked in F10; OAuth is an option, not a selected implementation.**
  Historical proposal: **Account claiming via Google OAuth** — the device token is the account today, so clearing cookies loses it and one person on two devices is two users. Schema is ready: `users.auth_provider` / `auth_subject` / `email` are nullable and `devices.user_id` is re-pointable, so this is ~120 lines of vanilla PHP plus a device-merge query, no migration.

- **Historical transferable link code assessment (2026-08-12).** Raised as "can't we use a browser
  signature so one browser doesn't make duplicate lists, and later let someone copy a token to
  another device". Two separate things; the first is a non-problem and the second is the OAuth
  item above without the OAuth.

  **There is no per-browser duplication to fix.** The prompt for this was ~40 near-identical
  public lists in the dev directory. Measured: 49 public lists across **49 distinct `user_id`s**,
  and zero duplicate `(user_id, source_tag)` pairs — `publish_bucket`'s one-list-per-bucket rule
  holds. They are automated test runs: `tests/test_lists_api.js` (nickname `tester`) and
  `tests/test_moderation.js` (`owner-mod-test`) each open a fresh cookie jar per run and say so
  in their own headers. A real browser holds one identity for 400 days. Cleanup:
  `DELETE FROM lists WHERE user_id IN (SELECT id FROM users WHERE nickname IN ('tester','owner-mod-test'));`

  **Browser fingerprinting is the wrong instrument, and would be worse than the status quo.**
  It fails in both directions and both are bad. *False merges:* two people on a shared laptop, or
  the same browser build behind one NAT, collapse into one account — and an account here is
  writeable data, so each could read and delete the other's marks and lists. *False splits:* the
  UA string changes on every browser update, so the signature drifts and mints a fresh user
  anyway — the exact failure it was meant to prevent, now silent instead of only on a cookie
  clear. It also breaks the test suite specifically: `test_moderation.js` needs two distinct
  users on one machine (an owner and a stranger) to assert you cannot report your own list, and
  fingerprinting collapses them. And it is a tracking technique on a site whose whole identity
  story is currently one random token. **Do not implement this.**

  **The transferable code is the right shape and the schema already carries it.** N `devices`
  rows may share one `user_id` and `devices.user_id` is re-pointable — the `_auth.php` header
  names this as the upgrade path. Nothing has ever used it: 858 users, 858 devices, exactly one
  each, because there is no endpoint to add a second. The real problem it solves is not
  desktop↔mobile so much as **clearing cookies loses everything, permanently, with no warning.**

  Design, when it is picked up:
  - **Never hand out the device cookie itself.** It is `httponly` precisely so JS cannot read it,
    and it is a 400-day permanent account key — pasted into a chat or caught in a screenshot,
    that is forever. Mint a *separate* link code: short-lived (~10 min), single-use, its own
    table with `expires_at` / `used_at`, redemption rate-limited through the existing
    `rate_limit()`.
  - **Generate on the device that holds the data, redeem on the empty one.** That direction makes
    the hard case rare.
  - **The merge is the actual work, not the token.** The redeeming browser usually already has an
    anonymous user with its own annotations. Three options: re-point the new device and abandon
    what it had; move the rows with last-write-wins (`store.js` already has those semantics from
    sync); or refuse to link when the target has data. Start with the first plus a plain warning —
    the second also needs conflict rules for `lists`, since two `fav` lists under one user breaks
    `publish_bucket`'s one-per-bucket assumption.
  - **It does not weaken the anti-abuse reasoning** recorded in CLAUDE.md and in the no-auto-hide
    note below. Linking lets many devices share one user; it does not let one device be many
    users. Votes are counted per user, so it slightly *reduces* inflation.
  - **No UI surface exists to hang it on.** Probably a "cont" block in the footer or a small
    settings page — that is a design decision, not a leftover.
- [ ] **Spaced repetition off `game_events`** — every answer is logged with word, correctness and response time. Enough to resurface words a user got wrong, and to compute a real per-word difficulty score (which is also a research signal: which "forgotten" words are genuinely unrecognisable).
- [ ] **Word difficulty stats** — aggregate `game_events` by word to show a global correct-rate. Feeds the stats page and could rank the shortlist by how forgotten a word actually is in practice, not just by corpus frequency.
- [ ] **JSON export button** — the data is already reachable via `api/sync.php` with `{"since":0}`; only a download button is missing. Closes the older "exported as json" item properly.
- [x] **Moderation for public lists** — Done 2026-08-07. `reports` table (app.db `user_version = 3`), `POST api/lists.php {action:'report', slug, reason?}`, a report link on `lista.php`, and `public/admin.php` as the review queue (unpublish / dismiss / delete) behind `OTIOS_ADMIN_TOKEN` in `config.local.php`. Covered by `tests/test_moderation.js`. See the "Moderation" section of CLAUDE.md for the two properties worth not undoing (404-not-403 for a bad token; token sealed into a cookie and redirected out of the URL).

  Two decisions recorded here because they'll look like omissions later:
  - **No auto-hide after N reports.** Identity is an anonymous device token, so N distinct reporters costs an abuser N cookie clears — a threshold would make censoring a list cheaper than publishing one. Reports queue for a human.
  - **`lista.php` does not check list ownership before showing the report button**, because that would mean calling `current_user()` on every public view and minting an identity for every passing crawler. The API rejects `own_list` and the button surfaces that.

  Still open: `liste.php` remains `noindex` — lifting it is now a product decision, not a blocker.
- [x] **Backups for `private/app.db`** — Done 2026-08-07. `php api/_backup.php` takes a `VACUUM INTO` snapshot into `<private>/backups/`, integrity-checks it, and prunes to the newest `--keep N` (default 14). CLI-only (`PHP_SAPI !== 'cli'` → 404 before any include), and it lives in `public/api/` because only the contents of `public/` reach the server. Cron line in CLAUDE.md.

  - **Open verification consolidated into [F10](fixes/F10-recovery.md): get a copy off the machine.** A snapshot beside the original survives a bad migration or a mistaken delete, not a lost disk. Either confirm the host's own backup covers `~/voroave-private/`, or add an rsync/rclone step after the cron line.
- [ ] **Verify WAL on the production host** — `app_db()` falls back to `journal_mode=TRUNCATE` when WAL is unavailable, which some NFS-backed shared hosts require. Check which mode is actually active after deploy: `PRAGMA journal_mode`.
- [ ] **`feed_decisions` is written by nobody yet** — the table exists for the swipe game's keep/skip record, but `app.js` `feedKeep()`/`feedSkip()` still only set a bookmark. Wire it up to get a second signal (explicit rejection) distinct from "never seen".

## UI/UX findings from the "beton" skin pass (2026-08-06)

Collected while building the brutalist skin (`feat/brutalist-skin`). Everything here is
*beyond* visual styling — the skin itself is done, these are the structural things it
kept bumping into. Roughly in order of how much they cost a first-time visitor.

### Content and language

- [x] **The `verdict` enum is rendered raw to users.** Fixed 2026-08-07. `VERDICTS` and
  `TIERS` in `api/_lib.php` are now the single source for label, abbreviation, tooltip and
  (for tiers) bar-fill class, consumed by `verdict_label()` / `verdict_abbr()` /
  `tier_label()`. Replaced **three** duplicated copies of the tier map (`index.php`,
  `stats.php`, `stats_panels.php`) and the hard-coded verdict list in `index.php`'s pill
  loop. The hover box was also printing the raw enum client-side; `word_row.php` now emits
  `data-vlabel` so `app.js` reads the label instead of mapping it a second time. Verified
  no enum survives in the visible text of `index` / `stats` / `joc` / the detail panel.
  `tier_label()` returns `''` for an unmapped key rather than the key itself — a bare enum
  on the page is worse than no chip.

  <details><summary>original report</summary>

  `_partials/detail.php:26` prints
  `historical_only` / `dex_absent_highfreq` / `corpus_historical_only` verbatim into the
  verdict badge and the `confidence_tier` chip, in an otherwise fully-Romanian UI.
  `index.php:166-171` already carries the human labels for exactly these four verdicts
  (`dispărut din uz`, `în declin`, `doar istoric`, `absent`) — they're just trapped in the
  filter-pill markup. Fix: one `verdict_label()` / `tier_label()` pair in `api/_lib.php`,
  consumed by the filter pills, the detail badge, the hover box and `word_row.php`'s
  `EXT`/`DEC`/`IST`/`ABS` abbreviations, so there's a single place to translate them.
  Deliberately *not* fixed in the skin branch — it's copy, and the wording is the owner's
  call. Note the brutal skin makes it more conspicuous: the badge is now a solid colour
  block, so a raw enum sits second in the visual hierarchy after the headword itself.

  </details>

  Labels used are the ones already written in `index.php`'s filter pills (`dispărut din
  uz` / `în declin` / `doar istoric` / `absent`); the three previously-English tier labels
  became `corp. dispărut` / `corp. în declin` / `corp. doar istoric`, keeping the existing
  `corp.` / `dex.` prefix pattern. No new copy was invented — see the `stats.php` entry
  below for the strings that were left alone precisely because they would need some.

- [ ] **`stats.php` is half-English.** `register: any`, `domain: any`, `etymology: any`,
  `dicts: any`, `TIER`, `POS`, `FILTER`, `reset`, `def ✓`, `loading…`, plus
  `stats_panels.php`'s `no data` and `No words match the selected filters.` The index
  page's equivalent rail is fully Romanian. (`word_list.php`'s two English strings were
  fixed on this branch; the rest were left alone for the same copy-ownership reason.)

  **The index page is not clean either** (found 2026-08-08): the sort `<select>` in the
  filter rail reads `↓ rarest modern` / `↓ most declined` / `↓ DEX frequency` /
  `↕ alphabetical` — four English strings in the most-used control on the site. Only
  `↓ cele mai potrivite` and the new `↑ ultima atestare` are Romanian. Same copy-ownership
  reason for leaving them; they belong in one pass with the `stats.php` list.

- [x] **Raw seam enum in the active-filter chip.** Fixed 2026-08-08. `AF_SPECS` printed
  `listă: curiosity` into an otherwise Romanian chip bar; it now uses the same labels the
  seam control itself carries (`relevante` / `curiozități`). Same family as the verdict-enum
  entry above — worth grepping for a third instance rather than waiting to spot one.

### Navigation and information architecture

- [x] **There is no shared header, and no consistent way to move between the four pages.**
  Done 2026-08-08, as **two** partials rather than one. `api/_partials/header.php` carries
  brand + three slots + the display preferences; `api/_partials/footer.php` carries the
  one navigation bar. All five pages adopted both, and `.joc-head` / `.joc-title` /
  `.joc-nav` / `.lista-nav` are gone from the pages *and* from `brutal.css` / `govuk.css`.

  **Why the split**, since the original entry asked for one partial with nav in it: the
  explorer's top bar already carries brand + search + count + play + view + scale + skin +
  theme + filters, and "the brand bar carries too much" is a live entry three sections
  down. Five nav links is the one thing it cannot take. `index.php` had already put nav in
  the bottom status bar, that bar is the right size for it, and it is thumb-reachable on a
  phone — so identity goes at the top and travel goes at the bottom, on every page. Below
  900px the nav drops to icons only, and the GitHub link (which has no icon of its own)
  hides.

  Two things worth not undoing:
  1. **The current page stays an `<a>`**, marked `aria-current="page"` and distinguished
     by an accent underline. It was briefly a `<span>`, which stopped matching every
     skin's `#status-bar a` rule and so needed a colour of its own — and `var(--text)`
     came out near-black on beton's ink footer. This is the `--bar-bg` / `--on-bar` trap
     already logged under "Skin ideas"; letting each skin's existing link rule apply is
     the version that survives a skin nobody has written yet.
  2. **`lista.php` deliberately sets no `$page`.** It is not `liste.php`, so nothing in
     the nav should render as current and stop being clickable.

  Found while adopting it: `kbd { display: none }` below 768px (pre-existing) left the `?`
  shortcuts link a **zero-width tap target** on mobile — and that modal is where the colour
  legend lives on narrow screens, since the footer legend hides below 1280px. It now falls
  back to the word "legendă" there.

- [ ] **`metodologie.html` is a separate product.** It links neither `app.css` nor
  `prefs.js`, loads a *different* font stack (Inter Tight + JetBrains Mono vs the app's
  Public Sans + IBM Plex Mono + Source Serif 4), and carries its own hand-copied theme and
  text-scale JS. It will not follow the skin toggle at all, so switching skins on the app
  and then clicking "metodologie" lands you somewhere visibly unrelated. Either fold it
  into the shared stylesheet or convert it to `metodologie.php` using the shared header.

### Filters

- [ ] **Every filter box starts checked, so the rail reads as a wall of "on".** With all
  verdicts, all five tiers and all eight parts of speech pre-selected, the selected state
  carries no information — you cannot tell at a glance what is *filtering* versus what is
  merely *available*, and the brutal skin's solid-ink checked pills make the wall literal.
  Worth considering: treat "all selected" as an implicit unfiltered state rendered
  neutrally, and only paint pills once the set is genuinely narrowed.

- [ ] **No "solo" or "none" affordance on the pill groups.** Isolating a single part of
  speech means unchecking seven boxes one at a time. A click-to-solo (like soloing a
  layer) plus a "none/all" control per group would turn the rail's most common task from
  seven clicks into one.

- [ ] **Filter state is invisible from the keyboard.** `?` documents navigation and the
  quick-tags but not the filter drawer; there's no shortcut to open/collapse the rail even
  though `toggleFilterDrawer()` already exists and the desktop rail is collapsible.

### Detail panel and reading flow

- [ ] **On mobile there is no way to preview a definition without committing.** Desktop
  gets `#hover-box` with a truncated preview; touch has no hover, so scanning 25k words
  means open → read → close → open. The arrow keys already move selection and the panel
  already follows it, so a compact "peek" row under each selected word — or making the
  bottom sheet a short peek that expands on drag — would make browsing far cheaper.

- [x] **Dead UI surface: notes and custom tags.** Partly fixed 2026-08-07 — the *notes*
  half was genuinely dead and is now gone end to end: `.fp-note textarea` and
  `#note-status` removed from `app.css`, and the `cu notă` option removed from the `marks`
  filter. Nothing could create a note and nothing displayed one, so filtering to "cu notă"
  showed words whose notes you couldn't read.

  **The tags half was not dead and was left alone**, which the original entry got wrong:
  `store.js:117` still renders `.tag custom-tag` chips for users who created custom tags
  before the input was removed, so that CSS is load-bearing. The `tag: …` options in the
  `marks` select are all live too — they come from `$QUICK_TAGS` (`ascunde`/`lol`/`meh`),
  which the quick-tag buttons still produce, plus `populateTagFilterOptions()` for legacy
  custom tags. Only `#tag-input`'s own rules are strictly orphaned, and they were kept
  since restoring the input is still an open option.

  Note server-side note storage is untouched: `sync.php` still round-trips `note`, so
  nobody's existing data was dropped — it is just no longer surfaced.

- [ ] **`ascunde` and `meh` are two buttons for one behaviour** (both hide the word and
  both exclude it from quiz rotation — see the quick-tag entry below). Known and
  deliberate, but it costs a button and an explainer paragraph; worth revisiting once
  there's data on which one people actually press.

### Accessibility

- [x] **`maximum-scale=1` blocks pinch-zoom on all four pages** — Fixed 2026-08-07.
  Removed from `index.php`, `joc.php` and `stats.php`; `lista.php` and `liste.php` never
  had it, so all five now agree. The in-app A−/A+ stepper stays as an addition to browser
  zoom, not a replacement.

- [x] **Word rows are non-focusable `<div>`s.** Done 2026-08-08 as a **listbox with a
  roving tabindex**, not `tabindex="0"` on every row: `#word-list` is `role="listbox"`,
  rows are `role="option"`, and exactly one row is tabbable at a time. Plain `tabindex="0"`
  everywhere would have been literally correct and unusable — with infinite scroll, Tab
  would walk thousands of words before reaching the footer.

  - Tab enters the list once and lands on the selected word (or the first).
  - `j`/`k`/arrows move selection *and* focus — but `selectRow()` only moves focus when
    focus was **already** on a row, so the same call made on page load from a `?word=`
    link doesn't yank the caret out of wherever the user is.
  - Enter and Space activate; Space is `preventDefault`ed so it doesn't scroll instead.
  - The mouse path now routes through `selectRow()` too. It used to set `data-selected`
    by hand, which after this change would have left the tab stop on the previous row.
  - Rows carry an explicit `aria-label` ("subdialect, doar istoric") and the chips are
    `aria-hidden` — otherwise a screen reader reads out "subdialect 89 s.f. IST 📚12".

  Also found: **`app.css` defined no `:focus-visible` at all** (only `brutal.css` did), so
  the moment rows became focusable there was a caret nobody could see. `.word-row:focus-visible`
  now draws an accent outline — kept separate from `[data-selected]`, because clicking
  selects without focusing and the two states are not the same thing.

- [x] **Toggle buttons don't expose their state.** Done 2026-08-08. `syncThemeButtons()`
  and `setView()` now set `aria-pressed` alongside the CSS class, and the icon-only
  buttons in the shared header carry `aria-label` as well as `title`. The class is what
  CSS reads, the attribute is what a screen reader reads, and only one of them existed.

- [ ] **In cloud view, verdict is encoded only as colour.** The square is the sole signal;
  table view additionally shows `EXT`/`DEC`/`IST`/`ABS`. Colour-blind users get nothing in
  the default view. **The screen-reader half is fixed** (2026-08-08 — the row's `aria-label`
  names the verdict), but the visual half is still open and is a *design* decision, not an
  accessibility patch: every fix changes how the cloud looks. Shape-coding the dot per
  verdict is the textbook answer but does nothing in `beton`, which drops the dot and
  colours the headword instead; showing the `EXT`/`DEC` abbreviation in cloud view fixes
  every skin but changes the density of the main view. Note desktop hover already names
  the verdict via `#hover-box`, so in practice the gap is **mobile cloud view**, which
  overlaps with the "no way to preview a definition without committing" entry above —
  worth solving together.

### Mobile

- [ ] **The brand bar carries too much.** Brand + search + play + view + scale + skin +
  theme + filters. Scale, skin and theme are all set-once preferences that could collapse
  behind one "⚙" sheet, leaving the bar for the three things people actually use while
  browsing (search, view, filters). The 320px overflow fixed on this branch was the
  symptom; the cause is that the bar is a settings panel wearing a toolbar's clothes.

- [ ] **The filter sheet's drag handle is decorative.** `.fs-handle` looks draggable and
  sits exactly where a sheet gesture belongs, but nothing listens for touch — the sheet
  only opens and closes via the button. Either wire it up or stop drawing it.

- [ ] **No end-of-list affordance.** Infinite scroll (`hx-trigger="intersect once"`) has no
  "that's all" state and no way to jump — with 25,217 words there is no pagination, no
  alphabet index, and no scroll position indicator beyond the browser's own scrollbar.

## Skin ideas (2026-08-06)

Each is one file in `public/assets/skins/` — see the "Visual skins" section of CLAUDE.md
and copy `_template.css`. `velin.css` shows that a skin can be tokens only, ~70 lines.

- [x] **GOV.UK** — done 2026-08-06 as `govuk.css` ("Guvern"). Answered the question it was
  picked for: tokens got the palette, the radius and the fonts, but not the black masthead,
  the yellow focus state, the square marks, the dotless tags, the green button's 2px edge,
  the always-underlined links or the inset rule. Only one of those looks like a missing
  token (a dot/mark radius, separate from `--radius`); the rest are genuinely
  component-shaped. So the contract is about as complete as it can usefully be.
- [ ] **monitorul.ai** — house style; useful for a family resemblance across the projects.
- [x] **dictionary.com / thesaurus.com** — done 2026-08-06 as `tezaur.css` ("Tezaur").
  Tinted synonym pills, rounded, big serif headword, POS in italic. The pill fill replaces
  the verdict dot. Was indeed the most usable of the set.
- [ ] **Urban Dictionary** — bold sans, heavy blue links, that hard yellow accent, thumbs.
  A joke skin that's also a good stress test: it wants a much denser, more cramped layout
  than the tokens currently allow.
- [ ] **Wikipedia** — Vector 2022: Linux Libertine headings, sans body, hairline rules, the
  pale blue link colour, generous white. Very close to `paper`, so mostly a type exercise.
- [ ] **Genius.com** — dark by default, the yellow-on-near-black, annotation highlights over
  text. The annotation-highlight idea maps unusually well onto this project, where words
  already carry marks (`inv`, `bookmarked`, quick-tags).

Two of these (Urban Dictionary, Genius) will probably need component rules and not just
tokens; if several skins end up reaching for the same missing hooks, that is a signal to
add tokens for those rather than to let each skin restate them.

Two hooks both new skins reached for, worth watching for a third taker:

- [ ] **A radius token for round marks**, separate from `--radius`. The verdict dot, the
  filter dot, the legend swatch and the checkbox are all hardcoded `50%` / `2px` in
  `app.css`; `govuk` squares all four by hand. Cheap to add once a second skin wants it.
- [ ] **Brand-bar-on-a-dark-ground tokens.** Both `brutal` (ink footer) and `govuk` (black
  masthead) had to restate every control in the bar because `--surface` / `--border` /
  `--text-*` are page-ground values. A `--bar-bg` / `--on-bar` pair would collapse ~25
  lines in each. Note the trap: `.skin-select` draws its caret with two `background-image`
  gradients, so anything touching it must set `background-color`, not `background`.

## stats.php chart colours are hardcoded (2026-08-06)

The TIER chart's bars pick up the verdict tokens and reskin correctly, but the
`parte de vorbire` (indigo) and `domeniu` (green) bars are fixed hex in `stats.php` and
stay the same under every skin. Noticed while checking `govuk`, which is otherwise
strictly black/white/blue. Low priority — the page reads fine — but it is the one place a
skin visibly does not reach.

Hit again by `registru` (2026-08-08), which is black/white/one-blue and where indigo and
emerald bars were by some distance the loudest thing on the stats page. That skin patches
both fills to `var(--text)` in its own file, so this is now worked around twice rather
than fixed once — two tokens (`--bar-pos`, `--bar-dom`, defaulting to the current hexes)
would retire it. Second skin to need it is usually the point to stop working around.

## Filter by dictionary — which one, and how recent (2026-08-06)

Counting dictionaries is already done: `dict_min` in the filter rail offers ≥3 / ≥6 /
≥10 / ≥15, backed by the `sources` column (pipe-separated) and `dict_count`. What's
missing is *which* dictionary and *how recent* — and the second is the more interesting
signal this project has not yet used.

Measured against `public/data/ui.db`: **73 distinct dictionaries**. The head is broad
(MDA2 23,235 words · DEX '09 18,097 · DOR 17,279 · DEX '98 16,740 · Ortografic 16,621 ·
DOOM 2 16,158 · DOOM 3 16,092 · DLRLC 15,934) and there is a long tail — roughly 30
dictionaries appear in fewer than 200 words each (DGL 2, Șăineanu ed. I 1, DEX '16 1).

- [ ] **Filter by specific dictionary.** A multi-select over the ~15 head dictionaries,
  with the tail collapsed or excluded. "Words in Șăineanu but not in DEX '09" is close to
  a definition of *forgotten* and the data already supports it — no new columns needed,
  just `sources LIKE` or a normalised join table. A join table is worth building at this
  point anyway: 73 values × 25k words is small, and `LIKE '%DEX '09%'` will mis-hit
  (`DEX '09` is a substring of nothing here, but `DOOM` is a prefix of `DOOM 2`/`DOOM 3`,
  and `MDA` of `MDA2`).

- [x] **Most-recent-attestation filter** — Done 2026-08-08. **The blocker this entry
  described was already gone and nobody had noticed.** It said "no year metadata
  anywhere … needs a hand-curated `dictionary → publication year` table", but
  `extract_dict_sources.py` had since learned to read `Source.year` (108 of 113
  dictionaries carry one), so `newest_dict_year` was already in `dict_sources.db`, already
  flowed through `make_shortlist.py` → `build_ui_db.py`, and was sitting in `ui.db` on
  **15,862 of 16,315 words (97%)**. A `grep` over `public/` found zero uses of it. No
  curation, no pipeline run, no new column — the signal had been paid for and never spent.

  Shipped as three things in `_lib.php` / `index.php` / `detail.php`:
  - `sort=attested` — `newest_dict_year ASC NULLS LAST, word ASC`. Nulls last on purpose:
    no year means the dictionary is unnamed or unmatched, not that the word is ancient.
  - `attested_before=<year>` — a filter offering 1970 / 1990 / 2005 / 2010, registered in
    `AF_SPECS` and both URL arrays so it is shareable.
  - "ultima atestare 1929" as the lead chip in the detail panel's dictionary row.

  **Read the seam caveat before using it as a headline number.** The `relevant` seam
  requires `in_current_dict` (2005+) to qualify, so it is 2,806 words at 2010+ and 9 below
  — this filter says almost nothing there *by construction*. It is a `curiosity`-seam
  instrument, and a good one: 225 curiosity words were last printed before 1970, and the
  top of that list is `bracă`, `bujdeucă`, `ciotură`, `desbatere`, `orândueală`,
  `răsvrătit`, `sburătoare`, `vuet`, `zeciueală` — all Șăineanu 1929, and a clean sweep of
  pre-1953-reform orthography. Incidentally this is also the cheapest route to the
  "make a list with *-ațiune" item below: `abilitațiune`, `insinuațiune`,
  `personificațiune` are all in the same slice.

- [ ] **Whether `last_attested_year` should replace the superscript.** Now that it is
  visible in the panel, the open question is whether it is a better *headline* number than
  the DEX frequency score currently in the superscript. Argument for: "ultima atestare
  1929" is a claim a reader can act on, where `89` is not. Argument against: 97% coverage
  means 3% of words would show nothing, and the distribution is bimodal (10,243 words at
  2021, 4,892 at 2010), so for two thirds of the list it would print the same two values.

## Typographic pass — remaining findings (2026-08-06)

Found while driving the pages through Playwright at 2× and measuring computed style
rather than eyeballing screenshots. The table-column drift, the tracking scale and the
colour emoji were fixed on this branch; these were measured or seen but left alone
because they are content/data decisions, not styling.

- [x] **Debug metrics are shipping to users.** Fixed 2026-08-07 by labelling rather than
  hiding: `zipf ro` / `zipf en` / `istoric` / `modern` / `raport`, each with a Romanian
  `title` explaining what it measures (ppm against which corpus, what the ratio is a ratio
  of). `.fp-stats em` margin went 1px → 4px, which was the "no space between label and
  value" half of the complaint. Kept visible rather than put behind a dev flag: this is a
  research tool and the numbers are the point — they were just unreadable.

- [ ] **Raw enum values reach the page in three more places.** Beyond the `verdict` badge
  already noted above: `corpus_historical_only` and `dex_invechit_absent` render as
  literal chips in the detail panel. The beton skin makes this louder, not quieter —
  these became solid blocks — but the fix is a label map, not CSS.

- [x] **`SINONIME — ÎN CURÂND` is a placeholder in production.** Dropped 2026-08-07, along
  with `.fp-syns-placeholder` in `app.css` and `brutal.css`. The synonyms work itself is
  still open — see the "synonyms data" entry under UI; the row comes back when there is
  data to put in it.

- [ ] **Definitions repeat verbatim.** `barabor` shows the same Ștețco 1990 citation three
  times in one panel, because sources are concatenated on `|` and near-duplicate entries
  aren't collapsed. Reads as a rendering bug even though it's a data-merge issue.

- [ ] **The joc play area is mostly void at desktop width.** The card is bottom-heavy in a
  tall empty column — roughly a third of the viewport is unused below it, with the card
  top-anchored. Needs a vertical centring decision, or a second element (progress, streak,
  the word's register) to justify the height.

- [ ] **The filter rail states the same control two different ways.** `NIVEL` is five
  full-width solid bars; `CATEGORIE` is a grid of small chips. Both are checkbox
  multi-selects. Since every box also starts checked, `NIVEL` reads as a wall of solid
  black that carries no information. Making them one control type would calm the rail
  more than any colour change.

- [ ] **`definiție` breaks the rail's label pattern.** Every other group has an uppercase
  mono tab above it; this one is a lowercase inline label beside its buttons, so the last
  row of the rail doesn't align with the twelve above it.

## Quick-tag redesign (2026-08-06)

- [x] **Collapse quick-tags to `fav / ascunde / lol / meh`, one row** — prompted by noticing `ignore`, `remove`, and `simple` all serve the same "shouldn't be in the list" goal. Analysis: today only `simple` has real backend behavior (excludes a word from quiz rotation, `quiz.php:102`); `ignore`, `remove`, `boring`, `funny` are free-form labels with no differentiated logic, even though an earlier backlog resolution (line ~179 above) assigned `ignore`/`remove` distinct *meanings* (not interesting to you / not genuinely forgotten) that were never actually enforced in code — i.e. they're functionally identical today.

  The quick-tags conflate two separate goals (per discussion): **(1) a corpus-quality signal** to fine-tune the shortlist — too common, or a bad/wrong entry — feeding back into curation; and **(2) a personal-favorites signal**, meant to be shareable, which is the project's viral hook (a "my favorite forgotten words" list). Recommendation was to split these into two small groups rather than one flat row of 5, but the user opted to keep it simple for now: one row of four — `[★] fav` (bookmark, existing) / `ascunde` (consolidates ignore+remove+simple — "uninteresting, too well known") / `lol` (renamed from `funny`) / `meh` (renamed from `boring`). Custom tag input + notes hidden for now — no clear consumer yet.

  **Open question raised while drafting the explainer copy**: draft text said words tagged `ascunde` **or `lol`** disappear from the list — but `lol` = "amuzant" is a positive vibe tag, so that reads like a typo for `meh` (whose own definition was written as "ascunde, said differently"). Resolved: `ascunde` + `meh` are the two hide/quality tags, `fav` + `lol` are the two keep/vibe tags.

  **Implemented 2026-08-06**: `ascunde`/`lol`/`meh` replace the old five quick-tags everywhere — `_lib.php` (`$QUICK_TAGS`, `$QUICK_TAG_EMOJIS`), `store.js` (`QUICK_TAG_EMOJIS`, `qtKeyToTag`), the quick-tag buttons in `detail.php`, the shortcuts legend and keyboard handler (`a`/`f`/`m`, freed up from the retired `ignore`/`boring`/`remove`/`simple` keys — `f` deliberately carried over from the old `funny` binding since `lol` is its direct descendant). `quiz.php`'s quiz-exclusion filter now excludes on `tag:ascunde` OR `tag:meh` (previously `tag:simple` only). Custom tag input + note textarea removed from the detail panel (still functional server-side/in `sync.php` for existing data, just no longer exposed in the UI). A dismissable `#qt-explainer` banner explains the four tags on first view, persisted via `localStorage['otios.qtExplainerDismissed']`; every quick-tag button also carries a `title` tooltip with the same explanation for after it's dismissed. `ascunde`+`meh` both get the stronger red "extinct" active color in `app.css` (was `remove`-only) to visually flag the hide action; `lol` keeps the default amber "tagged" color.

## Publishing a paper (2026-08-11)

- **Evaluation execution is tracked in [F09](fixes/F09-evaluation.md). Paper submission remains a separate later decision.**
  Full assessment in **`docs/publication-assessment.md`** — what is publishable (the
  paradigm rollup as a method; the four measured negative results — ppm across a 1,187×
  size gap, CoRoLa's 1945+ span, subtitle folk-music contamination, LUMRO authors-vs-novels;
  the 16,941-word resource), what blocks it, and candidate venues.

  The blocker is the same one `docs/conceptual-roadmap.md` §2 named and nobody has closed:
  **there is no evaluation against any ground truth.** `ARCHAIC_TAGS`
  (`make_shortlist.py:58`) is a *feature*, never held-out labels, so the project cannot
  currently say whether the corpus signal beats DEX `frequency` alone, beats `wordfreq`
  alone, or whether the hand-set `SCORE_*` weights beat uniform ones.

  First two steps are ~a day each and are worth doing **whether or not a paper happens** —
  they are the only way to know if the corpus half of the pipeline is earning its keep:

  1. hold out `învechit`/`arhaizant` as labels with those tags stripped from the features,
     report P/R/AUC;
  2. baselines — DEX frequency alone, `wordfreq` alone, modern count alone.

  Then: Beta-binomial bound on zero counts instead of the `hist_occ`/`hist_docs` floors
  (roadmap §5, and see the thin-corpus entry at the top of this file), a `SCORE_*` ablation,
  and a native-speaker "am auzit / n-am auzit" pass — note the existing four marks are
  aesthetic, not recognition, so that needs its own question.

  Licensing is a separate blocker for any dataset release: DEX dump, CulturaX and the LUMRO
  novels have three different answers, and the novels are the one that could stop it.

- [x] **`--star` is below AA in light mode on two skins** — measured 2026-08-11 with a
  Playwright contrast probe against the word row: `paper` **2.22:1**, `tezaur` **1.98:1**,
  with `registru` (4.10) and `velin` (3.26) passing only the 3:1 graphic bar. It is used by
  `.fav-star` (`app.css:1272`), the reader's own favourite marker, so this is a real
  legibility problem and not a theoretical one.

  Found while placing the curator-pick ★, which was moved to `--accent` instead (that clears
  4.5:1 in all six skins × both themes, worst case brutal light at 4.55:1). Deliberately not
  fixed at the same time: darkening `--star` enough for AA takes `#D4A017` to roughly
  `#8A6400`, which stops reading as gold — that is a palette decision across five skins, not
  a bug fix to fold into an unrelated change.

  **Fixed 2026-08-11 at 3:1, not 4.5:1, and the distinction is the whole fix.** `.fav-star`
  is a ★ *inside a button that says the word „fav" beside it* — the colour carries no
  information, so it is a graphical mark (WCAG 1.4.11) rather than text. At 4.5:1 the gold
  goes brown (`#D4A017` → `#8E6B0F`); at 3:1 it stays gold:

  | | was | now | |
  |---|---|---|---|
  | `app.css` (paper) | `#D4A017` | `#AE8313` | 2.22 → 3.03 |
  | `tezaur` | `#E0A106` | `#B38105` | 1.98 → 3.23 |
  | `velin` | `#B07A18` | `#AB7617` | 2.87 → 3.03 |

  Measured against the *button's* ground, not the page's — the first calculation used the
  row background and was off by ~0.2, which is the kind of error that makes a "fixed"
  contrast still fail. All six skins × both themes verified in-browser afterwards.

  The probe is ~30 lines of Playwright and worth keeping as a tool: it resolves a token to
  its computed colour, walks up for the first non-transparent ground, and prints the ratio
  per skin × theme. Would catch the whole class of "this skin looked fine while I was
  writing it alone" problems that the skins section of CLAUDE.md keeps naming.

- [x] **`rare_in_use` was full of common words (`credit`, `ecran`, `universitate`, `ceapă`)**
  — Fixed 2026-08-11. Three stacked causes, only two of them fixable:

  1. **The tier was built on a file that predated its own bug fix.**
     `forgotten_words_curated.csv` was dated **2026-05-16**; the taxonomy join fix
     (`2227ff5`, "correct join path via TreeEntry + MeaningTree") landed **2026-05-19**.
     `rare_words_wordfreq.csv` was regenerated on 9 June but *from* that stale input, so
     it inherited the pre-fix `dex_register` — the column this backlog already called
     noise. The instruction at the time ("re-run `validate_diachronic.py`") was followed
     for the shortlist; `create_curated_list.py` never was, so the rare branch sat on it
     for three months. Recomputing the gate with the fixed join: only **18 of 110** kept
     an archaic tag. Fixed by re-running the phase properly.
     Bonus: `dex_etymology` is populated for the first time (it was empty, which this
     backlog notes elsewhere as blocking etymology filtering).

  2. **DEX register tags are per-*meaning* and get collapsed onto the headword.** `atac`
     carries eight at once — `articulat`, `fonetică; fonologie`, `limba franceză`,
     `limba turcă`, `muzică`, `popular`, `regional`, `învechit`. Nothing is both French
     and Turkish; that is every sense of every entry flattened. One archaic sense makes
     the whole word `învechit`. Same bleed CLAUDE.md documents for `dex_pos`, which is
     why `dex_pos` uses `Lexeme.modelType` instead — `dex_register` has no such escape.
     **Not fixed, and not fixable without sense-level data.**

     Measured and rejected: requiring the archaic marker to be the *only* register tag.
     It cuts 593 → 318 and does not touch the problem — `tehnologie`, `tren`, `statut`,
     `consiliu`, `bloc`, `ambulanță` all carry `învechit` as their sole tag. It costs
     recall (`viteaz`, `Moldova; arhaizant; figurat; învechit`, is a good entry) and buys
     no precision.

  3. **`--upper-threshold 4.5` was not a rarity bound** — it admits 13–32 occurrences per
     million. Now **3.5** (≈3 per million), which is the only lever that works, because
     zipf is a usage measurement where the register tag is an editorial note about one
     sense. Default changed in `validate_with_wordfreq.py` so a re-run reproduces it.

  Tier: 110 → **290**. It grew because the old join produced false *negatives* as well as
  false positives. The low end is what the tier is for — `răgea`, `sfetnic`, `zidire`,
  `tină`, `braniște`, `baltag` — and the top still carries residual bleed (`dor`, `oaste`,
  `poruncă`), which is cause 2 and is documented rather than papered over.

- [ ] **`rare_in_use` is tiered on lemma zipf but displays surface zipf.**
  `validate_with_wordfreq.py` lemmatizes before the lookup (`atac` → `ataca`), while
  `build_ui_db.py` recomputes `zipf_frequency` on the surface form and overwrites it. So
  **15 of the 290** show `zipf 0.0` in the UI while sitting in a tier defined as
  `zipf ≥ 3.0`. Pre-existing (3 of the old 110) and small, but it means the number on the
  row is not the number that put the row there. Either tier on the surface form, or store
  the lemma zipf in its own column and show that.

- [ ] **`create_curated_list.py` emits inflected forms as headwords.** `țipând` (gerund),
  `citarea` (articulated infinitive), `patinoare` (plural), `ticăloasă`, `conductoare`,
  `moștenesc` are all in `rare_in_use` as if they were lemmas. Pre-existing — the old tier
  had `fotografia`, `japoneză`, `ardeleană`. `inflected_forms.db` already has the
  form→lemma map (1.63M rows) that would catch these.

- [x] **Tab-gated filter sections were wrong on every deep link** — Fixed 2026-08-11.
  `applyUrlToForm()` sets the radios without dispatching `change` (deliberately — a
  dispatch would fire a second htmx search on load), and the gating ran during script
  evaluation, when `word_tier` was still the markup default. So opening or reloading
  `?word_tier=rare_in_use` left **all three** sections in the other tab's state: `seam`
  and `clase` visible where they do nothing, and `#dex-rare-control` — the DEX ceiling and
  the loanword toggle — *hidden on the one tab where they work*. Clicking the tab was
  always correct, which is what kept this invisible.

  Fixed by naming the function `syncTabControls()` and calling it again after
  `applyUrlToForm()`. Also added `seam` to the tab guard in `activeFilterChips()`: it was
  the one tab-specific param missing there, so a URL carrying `seam=curiosity` onto the
  rare tab chipped „listă: curiozități" over a list that was never filtered —
  `build_word_filter()` has always ignored seam on that tab.

  This is the three-places rule in CLAUDE.md failing at a fourth place nobody had listed:
  the *initial* state, as distinct from the change handler.

- [x] **`rare_in_use` judged verbs by their infinitive** — Fixed 2026-08-11, and this was
  the real cause of the common words, not the tag bleed blamed earlier the same day.

  wordfreq measures surface strings. Romanian verbs are heavily inflected, so a citation
  form is systematically rarer than the verb: `mărturisi` 3.41 vs `mărturisit` 4.01,
  `asemăna` 3.11 vs `aseamănă` 3.79, `păți` 3.08 vs `pățit` 3.87. Judging a lemma by its
  infinitive calls every common verb rare — **the exact mistake CLAUDE.md already names
  for the corpus side** ("always roll them up through `inflected_forms.db`, or every verb
  reads as extinct"). The rare branch never got that rollup.

  Second failure, same fix: the gate ran on *simplemma's* lemma, and the lemmatizer picks
  homograph verbs — `secret` (4.75) → `secreta` "to secrete" (3.15), `dor` (4.50) →
  `durea`, `greșit` (4.67) → `greși`, `ceartă` (4.00) → `certa`. It was testing a
  different word. Keying the rollup on the surface form uses DEX's own paradigm, which
  cannot drift like that.

  `paradigm_zipf()` takes the **max** Zipf over the headword's whole DEX paradigm — max,
  because the question is "is any form of this in current use?", and Zipf is a log scale
  so summing it means nothing. Computed lazily (only rows that clear the floor *and* carry
  an archaic register can reach the branch), which is ~17s over 145k candidates instead of
  walking the paradigm table for every row.

  299 → **219**. Gone: `secret`, `dor`, `greșit`, `ceartă`, `cronică`, `spori`, `oaste`,
  `poruncă`, `viteaz`, `mărturisi`, `înainta`, `păzi`, `topi`, `închina`, `asemăna`.
  Kept: `aba`, `aman`, `amanet`, `bacșiș`, `balaban`, `baltag`, `bir`, `beletristică`,
  `sfetnic`, `braniște`, `zidire`, `răgea`.

  **Residue, characterised:** archaic nouns that are homographs of common verb forms —
  `judec`, `leg`, `ucid` are DEX nouns (modelType M/N, so the `T`/`IL` filter does not
  catch them) whose spelling is also a 1st-person verb form, and wordfreq counts both. Not
  separable without sense-level frequency data. Plus the irreducible tag bleed
  (`abatere`, `balsam`, `berbec`, `bici` — one archaic sense among many).

- [x] **The „rare" tab is gone; `urme azi` replaces it** — 2026-08-11.

  It was measuring with a ruler that stops above the range it needed. Two rules decided
  the tab: DEX marks a meaning old, *and* wordfreq scores the word 3.0–3.5. Rule 2 cannot
  work. Measured across 60,000 candidates:

  | wordfreq Romanian score | words | |
  |---|---|---|
  | exactly 0.00 | 59,785 | 99.6% — the library has never heard of them |
  | anything at all | 215 | 0.4% |

  So its lowest *real* scores are ordinary words (`haz` 3.31, `bețiv` 3.22, `ocoli` 3.37),
  while `zapciu`, `vornic`, `logofăt` and `ispravnic` are all 0.00 — indistinguishable
  from each other and from every other word it does not know. A tier defined on that band
  could only hold common words, at any threshold. Three threshold changes on 2026-08-11
  were all tuning the wrong instrument.

  Two further facts settled it. The tab had **zero overlap** with the shortlist: all 219
  rows were words this pipeline had already measured against 17B tokens of CulturaX and
  correctly called still-used (`haz` has 62,021 modern occurrences). And the idea it was
  reaching for already had a population in the main list.

  **Replaced by `modern_band`** — a select (`urme azi`) over three buckets derived from the
  corpus. Direction matters and reads backwards: band 2 is `zapciu`, `birjă`, `vechil`,
  `dorobanț`, `jupâneasă`; band 0 is `celșag`, `racaleț`, `oglavă`, `barabor`. Edges come
  from `scaled_modern_thresholds()` at build time, never from a number in PHP.

  **Deleted with it:** the `word_tier` tier switch, `dex_max`, `hide_loanwords`,
  `#dex-rare-control`, and the whole tab-gating apparatus — three sections kept in step by
  hand across three places, which was wrong in all three on any deep link. Old
  `?word_tier=rare_in_use` links now land on the list rather than returning nothing.
  `validate_with_wordfreq.py` stays on disk as the standalone screen it is documented to
  be; it feeds nothing.

  Left open: `en_zipf` is now an unused column (its only consumer was `hide_loanwords`),
  and `docs/archive-obsolete/wordfreq-recipe.md` still describes the tab as live.

- [x] **The `zipf` explore filter was removed on 2026-08-11.** Historical diagnosis follows; see the completed entry below. 17,533 of 17,577 words score
  exactly `0.00` — wordfreq has no Romanian data for them — so `zipf_min` above zero leaves
  **44** words out of 18,270. It is the last place wordfreq still touches the UI, and the
  same resolution problem that got the „rare" tab deleted: the library's Romanian
  vocabulary bottoms out well above the range this project cares about.

  Options: drop `zipf_min`/`zipf_max` from the sheet; or relabel it honestly as "wordfreq
  knows this word" (a 44-word set, which is at least a true statement); or keep the column
  and stop offering it as a filter. Any of the three beats a slider that looks continuous
  and has two states.

- [x] **Retaining the unused `en_zipf` column is a closed decision.** The detail-display question remains open separately. Its only consumer was `hide_loanwords`, removed
  with the rare tab. `en_zipf >= 4.0` matches **0** of the 18,270 words on the list (724
  have any value at all), so it cannot come back as a filter here without first finding a
  population it separates.

- [x] **The `zipf` explore filter is removed** — 2026-08-11. wordfreq scored 17,533 of
  17,577 words at exactly `0.00`, so any floor above zero left 44 rows out of 18,270. Same
  call already made for `hide_loanwords` and for `proper_noun_like` as a browsing filter:
  a control that reveals nothing is worse than no control. The `zipf_frequency` column
  stays; it is simply not offered as a filter.

- [x] **Closed as won't-fix: inflected forms as headwords.** Measured 2026-08-11 against
  the rebuilt shortlist: **80 words** whose only DEX `modelType` is `T`/`IL`, **none of
  them in the `relevant` seam**, and most are legitimate nominalised infinitives
  (`zimbire`, `trândăvire`, `dormire`, `spășire`) rather than junk. The real offenders
  (`țipând`, `citarea`, `patinoare`) were in the deleted `rare_in_use` tier and went with
  it. Not worth a pipeline change.

- [x] **Closed as won't-fix: dropping the `en_zipf` column.** It is inert — its only
  consumer was `hide_loanwords` — but a column costs nothing and a schema migration for
  zero benefit costs more. The rule that matters is written down instead: `en_zipf >= 4.0`
  matches 0 of the 18,270 words here, so it cannot come back as a filter without first
  finding a population it separates.

- [ ] **The detail panel still shows `zipf ro` / `zipf en`.** Noticed 2026-08-11 while
  screenshotting for the Despre page: the metrics row prints `zipf ro 0.0  zipf en 0.0` for
  essentially every word, because wordfreq has no Romanian data for 17,533 of 17,577 of
  them. It is the same dead signal the explore filter was removed for, still rendered as
  though it meant something. Either drop the two figures from the row or show them only
  when non-zero.

- [x] footer vertical padding on mobile (re-opened 260812) — the earlier
  „make footer more compact" fix never reached the phone. `--statusbar-h` reserved 96px
  for a 47px bar at ≤480px and 76px for a 21px bar at 481–710px: 49–56px of blank page
  above the footer on every phone-sized window, invisible as a bug because the list just
  looks like it ends early. Right-sizing the constants was not enough — the bar's height
  moves by *reflow* (one line at 540px/100%, two at 540px/125%), so 16 of 90 skin × width
  × text-scale combinations still under-reserved. `prefs.js` now measures the rendered bar
  with a `ResizeObserver` and writes the token back; over-reservation is ≤1px across the
  matrix. The hard `height` on `#status-bar` is gone with it, which also stopped it
  clipping controls silently. See **`--statusbar-h` is measured, not declared** in
  CLAUDE.md; pinned by `tests/test_footer_metrics.js`.

- [x] **The row superscript should count historical attestation, not DEX frequency**
  — Fixed 2026-08-14. Two findings, one of which was a live bug that stood on its own.

  **(a) One tooltip still states the backwards reading.** `public/api/_partials/word_row.php:53`
  renders, on every row: `title="Frecvență DEX: 96/100 — cu cât e mai mic, cu atât cuvântul
  e mai rar"`. That is exactly the misreading the rest of the site was already corrected to
  avoid — `index.php:604-606` even carries a code comment saying *„Not «cu cât e mai mic, cu
  atât e mai rar», which is what this said"*, and `index.php:437` and `despre.html:375` both
  word it correctly. The row tooltip was missed in that pass. `zapciu` (dispărut din uz) is
  96 and `internet` is 88; the number is lexicographic prominence, not rarity. **Fix this
  string regardless of whether (b) is done.**

  **(b) The chip barely discriminates where people look.** Distribution of `dex_frequency`
  on the current build:

  | band | whole table | default view (`seam=relevant`) |
  |---|---|---|
  | 0.8–1.0 | 12,670 / 18,270 (69%) | 3,193 / 3,499 (91%) |

  In the default view it is a superscript reading 82, 91, 88, 93, 87 down the column — a
  number that costs a sentence of explanation to not be misread, and then says almost
  nothing.

  **What it is *not* replaced by: Zipf.** 38 of 18,270 words have a nonzero
  `zipf_frequency`; wordfreq has no Romanian data for the rest. That is why the zipf range
  filter was already removed from the sheet (see the entries above). It is not a candidate
  and must not be proposed as one again.

  **`newest_dict_year` is also not a candidate** as a row chip: in the relevant seam 2,727
  rows say 2021 and 731 say 2010 — two values cover 99%. It is a curiosity-seam instrument,
  as CLAUDE.md already states, and stays where it is (detail panel, `sort=attested`).

  **Decision: swap the chip to `hist_occ`, demote `dex_frequency` to the detail panel.**
  `hist_occ` is the signal `make_shortlist.score` already leans on hardest (`politeță` 143
  vs `celșag` 4), it points the right way with no caveat, it is self-explaining in one
  clause, and it has real spread in the default view:

  | `hist_occ` | 3–4 | 5–9 | 10–24 | 25–99 | 100+ |
  |---|---|---|---|---|---|
  | relevant seam | 710 | 1,116 | 996 | 536 | 141 |

  Its one weakness: across the whole table 5,367 words sit at `0`, so outside the default
  view a third of rows would show a bare `0`. Decide between rendering nothing at 0 (like
  `chip-dict`, which is already `if ($dict_count > 0)`) and rendering the `0` as a real
  statement — prefer the former; a blank is honest and a `0` invites "rarest" again.

  **No pipeline change is needed.** `hist_occ` is already a column in `ui.db` and is already
  selected by the list query. This is a UI-copy change end to end.

  **Every explainer has to move with it — this is the largest part of the task, not an
  afterthought.** The DEX number is currently explained in five places and they must not be
  left disagreeing (which is how (a) happened in the first place):

  1. `public/api/_partials/word_row.php:53` — the chip and its `title`.
  2. `public/index.php:550` — the footer legend strip (`<i class="lg-freq">42</i>frecvență DEX`).
  3. `public/index.php:604-610` — the `?` shortcuts-modal legend row, including its link to
     `metodologie#frecvente` and the code comment above it.
  4. `public/despre.html:373-377` — the same legend row, hand-copied into the static page
     (the file's own header comment says it is hand-maintained). It links `metodologie#frecvente`.
  5. `public/metodologie.html:951-995` — the `#frecvente` section, „Cele două frecvențe: DEX
     și Zipf". Needs the most work: its intro claims *„Amândouă se pot filtra în panoul
     explore"*, which is **already stale** (the zipf filter is gone), and the „scara" row
     says the DEX score is *„afișată 0–100 (exponentul mic de lângă cuvânt)"* — which stops
     being true the moment the chip changes. The paragraph ending *„Oțios apare deci ca
     **85**"* is keyed to the chip too and needs rewriting or moving.

  Also check, but probably leave alone: `public/api/_partials/detail.php:169` (the `zipf ro`
  chip — that is the separate open entry above), the `dex_freq` sort option
  (`index.php:214`, `_lib.php:28`) and the `dexfreq_min`/`dexfreq_max` range filter
  (`index.php:440-445`, `_lib.php:932-936`). Those stay: the filter sheet's own explainer at
  `index.php:437` already words the caveat correctly, and „intervale numerice brute, pentru
  cine vrea să sape" is the right home for a number that needs a caveat. The chip is not,
  because it has no room for one.

  **Do not add a second number.** The row already carries the verdict dot, the verdict
  abbreviation, `chip-meta`, `chip-dict` and optionally `chip-pick`; `--word-col` is sized
  against that chrome (see the comment at `app.css:39`). This is a swap, one slot.

- [ ] **Remote app.db has three `pax1` users** (ids 1, 360, 373 — one person, three device tokens, 67/126/390 marks). `export_editorial.py --user N` must pick one; marks split across users also inflate `/colectii` distinct-person counts. Worth consolidating into one user (careful: that changes n_up counts site-wide) or at least deciding which id is canonical.


Historical API lead: `dexonline.ro/definitie/<cuvant>?format=json`. Verify its current contract before adopting it;
the existing JSON/XML research item above tracks this work. No duplicate task is opened here.
