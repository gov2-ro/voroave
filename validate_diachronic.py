#!/usr/bin/env python3
"""
Diachronic comparison: historical (Wikisource) vs modern (CulturaX) corpus frequencies.

For each DEX candidate, compares how much of the historical corpus it accounts for
against how much of the modern one it does, and returns a verdict.

Two things make the comparison honest, and both were added in the 2026-08-07 rescore:

1. **Counts, not ppm.** The corpora differ by 1,187× in size (14.3M vs 17.0B tokens),
   so the old shared `0.1 ppm` floor meant "fewer than 1,697 modern hits" on one side
   and "at least 1.43 historical hits" on the other. `zapciu`, with 1,322 modern
   occurrences, was classified `extinct`. Thresholds are now occurrence counts.

2. **Paradigms, not citation forms.** The corpus processors count raw tokens, so an
   inflected lemma was only credited with the one form that happens to be its headword
   (`înmărmuri` 317, while `înmărmurit` alone is 5,846). Counts are now rolled up over
   `InflectedForm` paradigms — see `aggregate_by_family`.

The historical-vs-modern comparison itself uses `rank_shift`: the word's percentile rank
within each corpus, subtracted. A rank is scale-free, so the smaller corpus's resolution
floor no longer decides the outcome. `log_ratio` is still emitted for comparison.

Verdicts (all from paradigm-level counts):
  alive            modern_occ >= 1000 — in use today, whatever the history says
  emerging         alive, and relatively more prominent now than historically
  absent           no historical footing (< 3 occurrences or < 2 documents), not common now
  extinct          historically attested, zero modern occurrences
  historical_only  historically attested, fewer than 200 modern occurrences
  declining        historically attested, 200–999 modern, and fell >= 0.15 in rank

Only `extinct`, `historical_only`, `declining` and `absent` reach the UI; `make_shortlist.py`
drops the rest (see VERDICTS in public/api/_lib.php).

Usage:
    python validate_diachronic.py               # curated candidates only
    python validate_diachronic.py --all-dex     # every DEX word in either corpus
    python validate_diachronic.py --smoothing 0.5 --output path/out.csv
    python validate_diachronic.py --top 30      # print top-30 in summary

Requires process_wikisource.py / process_culturax.py, plus extract_inflected_forms.py
and extract_dict_sources.py for the paradigm and dictionary-year columns.
"""

import argparse
import csv
import math
import sqlite3
import unicodedata
from pathlib import Path

from constants import TAG_FAMILY_BY_ID, TAG_FAMILY_BY_PARENT, tag_family

LEXEMES_DB    = Path('data/processed/lexemes.db')
FREQ_DB       = Path('data/processed/corpus_frequencies.db')
CURATED_CSV   = Path('data/processed/forgotten_words_curated.csv')
OUTPUT_CSV    = Path('data/processed/forgotten_words_diachronic.csv')
DEFINITIONS_DB = Path('data/processed/definitions.db')
DEX_SQL_PATH   = Path('data/dictionaries/dex-database.sql')

_DEF_INSERT_PREFIX = "INSERT INTO `Definition` VALUES "


def _load_dict_counts(sql_path: Path) -> dict[str, int]:
    """Count distinct source dictionaries per headword from the Definition table.

    Streams the MySQL dump and reads only columns 2 (sourceId) and 3 (lexicon)
    from each row, skipping the large internalRep field for speed.
    Returns {normalized_word: count_of_distinct_dicts}.
    """
    if not sql_path.exists():
        return {}

    word_sources: dict[str, set] = {}
    n_prefix = len(_DEF_INSERT_PREFIX)

    with open(sql_path, encoding='utf-8', errors='replace') as f:
        for line in f:
            if not line.startswith(_DEF_INSERT_PREFIX):
                continue
            s = line[n_prefix:].rstrip('\n')
            if s.endswith(';'):
                s = s[:-1]
            i = 0
            n = len(s)
            while i < n:
                # find tuple start
                while i < n and s[i] != '(':
                    i += 1
                if i >= n:
                    break
                i += 1  # skip '('

                # skip column 0 (id) and column 1 (userId) — integers
                for _ in range(2):
                    while i < n and s[i] not in (',', ')'):
                        i += 1
                    if i < n and s[i] == ',':
                        i += 1

                # column 2: sourceId (integer)
                sid_start = i
                while i < n and s[i] not in (',', ')'):
                    i += 1
                source_id = s[sid_start:i].strip()
                if i < n and s[i] == ',':
                    i += 1

                # column 3: lexicon (quoted string or NULL)
                lexicon = None
                if i < n and s[i] == "'":
                    i += 1
                    buf: list[str] = []
                    while i < n:
                        c = s[i]
                        if c == '\\' and i + 1 < n:
                            nxt = s[i + 1]
                            buf.append("'" if nxt == "'" else ('\\' if nxt == '\\' else nxt))
                            i += 2
                        elif c == "'":
                            i += 1
                            break
                        else:
                            buf.append(c)
                            i += 1
                    lexicon = ''.join(buf)
                elif s[i:i+4] == 'NULL':
                    i += 4

                if lexicon and source_id:
                    norm = normalize(lexicon)
                    if norm not in word_sources:
                        word_sources[norm] = set()
                    word_sources[norm].add(source_id)

                # skip past the rest of this tuple (internalRep etc.)
                depth = 1
                in_str = False
                while i < n and depth > 0:
                    c = s[i]
                    if in_str:
                        if c == '\\' and i + 1 < n:
                            i += 2
                        elif c == "'":
                            in_str = False
                            i += 1
                        else:
                            i += 1
                    else:
                        if c == "'":
                            in_str = True
                            i += 1
                        elif c == ')':
                            depth -= 1
                            i += 1
                        else:
                            i += 1

    return {w: len(srcs) for w, srcs in word_sources.items()}


# dexonline renders entries that have a headword but no meaning body as
# "[Fără definiție.]". When that placeholder *leads* the text (only usage
# citations follow) the word has no real definition; when it appears mid-text
# as one sense among many, the word does. See BACKLOG #17.
_PLACEHOLDER_DEF_PREFIX = "[fără definiț"


def is_placeholder_definition(text) -> bool:
    """True when `text` is missing or only a '[Fără definiție.]' placeholder."""
    if not text or not text.strip():
        return True
    return text.strip().lower().startswith(_PLACEHOLDER_DEF_PREFIX)


def _load_definition_words(db_path: Path) -> set[str]:
    if not db_path.exists():
        return set()
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute("SELECT word, definition FROM definitions").fetchall()
    conn.close()
    return {normalize(w) for w, d in rows if not is_placeholder_definition(d)}

HIST_CORPUS     = 'wikisource_ro'
LUMRO_CORPUS    = 'lumro_ro'
MODERN_CORPUS   = 'culturax_ro'
SUBTITLE_CORPUS = 'subtitle_ro'

# The historical side is a *panel*, not one corpus. Wikisource is broad, undated and
# noisy; LUMRO is 175 dated novels by 111 authors (1845–1920), counted by the same
# tokenizer against the same DEX lookup set, so the two are addable. Both are raw text
# rolled up through our own paradigms — unlike CoRoLa, whose lists arrive already
# lemmatized by someone else's lemmatizer and therefore cannot simply be joined on the
# headword (see process_corola.py and docs/corpus-expansion-plan.md).
HIST_CORPORA = (HIST_CORPUS, LUMRO_CORPUS)

# CoRoLa is loaded (process_corola.py) and deliberately **not** in the modern panel.
#
# It was wired in on 2026-08-11 and taken back out the same day, on measurement. The
# reason is not the legal skew and not the lemmatization — the surface-form lists solved
# that one, and our own paradigms put `strugur`'s count back on `strugure`. It is the
# time span: **CoRoLa covers 1945 to the present**, so it is a reference corpus of the
# last eighty years, not a picture of current usage. Against CulturaX, per token:
#
#     condițiune  112.8×    comisiune  49.6×    dorobanț  41.1×
#     poemă        23.3×    iscăli     15.7×    dijmă      8.3×
#
# `condițiune` and `comisiune` are pre-1953-reform spellings; a corpus starting in 1945
# necessarily contains them. Summing it into `modern_occ` therefore reads mid-century
# literature as present-day life, and it removed 35 words from the *relevant* seam —
# `birjă`, `dorobanț`, `vechil`, `dijmă`, `cocoană`, `iscăli` — which is the project's
# best material disappearing from the default view.
#
# The frequency lists carry no dates, so a post-2000 slice cannot be taken. Using CoRoLa
# needs a third panel ("attested in the reference corpus") with its own meaning, not a
# term added to the modern one.
COROLA_CORPUS  = 'corola_ro'
MODERN_CORPORA = (MODERN_CORPUS,)

SMOOTHING = 0.1   # per-million tokens; floor for log ratio

RARITY_BINS = [(0.30, 'very_rare'), (0.50, 'rare'), (1.01, 'uncommon')]

# ── Occurrence thresholds ────────────────────────────────────────────────────────
#
# These replace the old per-million thresholds, which compared two corpora that differ
# by 1,187× in size using the same absolute 0.1 ppm floor:
#
#     culturax_ro   16,969,999,321 tokens  →  0.1 ppm = 1,697 occurrences
#     wikisource_ro     14,297,033 tokens  →  0.1 ppm =     1.43 occurrences
#
# So "absent from modern Romanian" used to mean "fewer than 1,697 web hits" (zapciu, at
# 1,322, was classified extinct) while "historically attested" meant two Wikisource hits.
# Counting occurrences directly is scale-free and says what it means.
#
# Calibrated by sampling the shortlist at each band of the disambiguated count
# (see docs/activity-history.md):
#   0         hărățire, zalisi, blănuire, alegădi, berbelâc        — dead
#   1–19      scoborâre, cârcioc, zânitură, mâglă, zapcierie       — dead
#   20–199    madmoazelă, gheșeftar, evhologhion, zulie, stoliță   — genuinely rare
#   200–999   jiliște, civilizațiune, docar, plevușcă, calabalâc   — rare, still readable
#   1k–3k     lehuzie, arhaism, stăvilar, căldăraș, colindător     — borderline
#   3k+       despotic, verișoară, călăreț, harababură, foiță      — alive
MODERN_RARE_OCC  = 500    # below this, genuinely rare in modern Romanian
MODERN_ALIVE_OCC = 2000   # at or above this, the word is simply in use

# Those two numbers were calibrated against CulturaX alone, at this size. An absolute
# occurrence count only means something relative to how much modern text was read, so
# when the modern panel grows the bar has to grow with it — otherwise *adding* a corpus
# makes every word look more alive, and every word sitting within the growth margin of a
# threshold crosses it for no reason but arithmetic.
#
# Measured when CoRoLa joined the panel (+3.8% tokens): 820 words left the shortlist, and
# they clustered at modern_occ 1991–1998 — directly under the 2,000 floor. That is drift,
# not evidence. `scaled_modern_thresholds()` rescales both bars by actual panel size, so
# the calibration above keeps meaning what it meant when it was sampled.
#
# This is not the ppm mistake in the comment above. That one compared *two panels of
# wildly different sizes to each other*; this holds one panel's own bar steady as the
# panel grows.
CALIBRATION_MODERN_TOKENS = 16_969_999_321   # culturax_ro alone, the sampled baseline


def scaled_modern_thresholds(modern_tokens: int) -> tuple[int, int]:
    """(rare, alive) occurrence floors, rescaled to the current modern panel size."""
    if not modern_tokens:
        return MODERN_RARE_OCC, MODERN_ALIVE_OCC
    scale = modern_tokens / CALIBRATION_MODERN_TOKENS
    return round(MODERN_RARE_OCC * scale), round(MODERN_ALIVE_OCC * scale)

# A single hit in a 14M-token corpus is noise, not attestation.
HIST_MIN_OCC  = 3
HIST_MIN_DOCS = 2

# How far a word must fall in relative standing between the two corpora to count as
# declining. Applied to percentile ranks, so it is independent of corpus size.
RANK_SHIFT_DECLINING = 0.15

INFLECTED_DB = Path('data/processed/inflected_forms.db')
DICT_SOURCES_DB = Path('data/processed/dict_sources.db')


def normalize(text: str) -> str:
    return unicodedata.normalize('NFC',
        text.lower().replace('ş', 'ș').replace('ţ', 'ț'))


def rarity_category(freq: float) -> str:
    for ceiling, label in RARITY_BINS:
        if freq < ceiling:
            return label
    return 'uncommon'


def get_corpus_tokens(conn: sqlite3.Connection, corpus_name: str) -> int:
    """Return total tokens for the most complete run of a corpus."""
    row = conn.execute("""
        SELECT tokens_processed
        FROM processing_stats
        WHERE corpus_name = ? AND status = 'completed'
        ORDER BY documents_processed DESC, completed_at DESC
        LIMIT 1
    """, (corpus_name,)).fetchone()
    return row[0] if row else 0


def load_dex_candidates(lexemes_db: Path, curated_only: bool,
                        curated_csv: Path) -> dict[str, dict]:
    """Return {normalized_word: {dex_frequency, description, rarity_category}}."""
    if curated_only:
        if not curated_csv.exists():
            raise FileNotFoundError(f'Curated list not found: {curated_csv}')
        candidates: dict[str, dict] = {}
        with curated_csv.open(encoding='utf-8') as f:
            for row in csv.DictReader(f):
                w = normalize(row.get('word_no_accent') or row.get('word', ''))
                if not w:
                    continue
                candidates[w] = {
                    'dex_frequency': float(row.get('frequency') or 0),
                    'description': row.get('description', ''),
                    'rarity_category': row.get('rarity_category', ''),
                }
        return candidates

    conn = sqlite3.connect(lexemes_db)
    rows = conn.execute("""
        SELECT DISTINCT lower(formNoAccent), frequency, description
        FROM Lexeme
        WHERE frequency > 0.01
          AND LENGTH(formNoAccent) > 2
          AND description != ''
          AND description IS NOT NULL
    """).fetchall()
    conn.close()
    out = {}
    for r in rows:
        w = normalize(r[0])
        if not w:
            continue
        freq = float(r[1]) if r[1] not in (None, '') else 0.0
        out[w] = {
            'dex_frequency': freq,
            'description': r[2] or '',
            'rarity_category': rarity_category(freq),
        }
    return out


def load_corpus_freqs(conn: sqlite3.Connection,
                      corpus_name: str) -> dict[str, tuple[int, int]]:
    """Return {word: (occurrence_count, document_count)} for one corpus."""
    rows = conn.execute("""
        SELECT word, occurrence_count, document_count
        FROM corpus_word_frequency
        WHERE corpus_name = ?
    """, (corpus_name,)).fetchall()
    return {r[0]: (r[1], r[2]) for r in rows}


def load_form_lemma_map(db_path: Path) -> dict[str, list[str]]:
    """Return {inflected_form: [lemma, ...]} from inflected_forms.db.

    Run `extract_inflected_forms.py` to build it. Returns {} with a warning if absent,
    in which case the family columns fall back to the bare citation-form counts.
    """
    if not db_path.exists():
        print(f'  [inflection] {db_path} not found — run extract_inflected_forms.py to '
              f'enable lemma aggregation. Falling back to citation-form counts.')
        return {}
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute('SELECT form, lemma FROM form_lemma').fetchall()
    except sqlite3.OperationalError:
        print(f'  [inflection] {db_path} has no form_lemma table — rebuild it.')
        return {}
    finally:
        conn.close()
    out: dict[str, list[str]] = {}
    for form, lemma in rows:
        out.setdefault(form, []).append(lemma)
    return out


SHARE_ALPHA = 1.0        # smoothing when splitting an ambiguous form's count


def aggregate_by_family(freqs: dict[str, tuple[int, int]],
                        form_lemma: dict[str, list[str]]) -> dict[str, tuple[int, int]]:
    """Roll citation-form counts up to whole paradigms: {lemma: (occurrences, documents)}.

    Romanian is heavily inflected and the corpus processors count raw tokens, so a lemma
    is otherwise only ever credited with its citation form:

        înmărmuri  317  →  6,376   (înmărmurit alone is 5,846)
        cătrăni     59  →  1,825

    Every verb was therefore pushed toward `extinct`.

    **Ambiguous forms are split, not duplicated.** ~12% of surface forms are claimed by
    more than one lemma, and naively crediting each claimant produces nonsense: `veșcă`
    (the rim of a sieve) shares its plural `vești`/`veștile` with `veste` (news), and
    would inherit all 339,710 of its occurrences.

    Each shared form's count is divided between claimants in proportion to how often each
    lemma's *own headword* appears in the corpus. That prior is what tells the two apart:

        vești     → veste 576,766 vs veșcă 264      → veste takes ~99.9%
        politețe  → politețe 33,178 vs politeță 280 → politețe takes ~99.2%

    (Weighting by "forms only one lemma claims" was tried first and fails: a noun's own
    citation form is frequently shared too — `veste` is claimed by both `veste` and
    `vestă` — so the evidence is empty for exactly the words that need it, and the split
    lands on whichever lemma happens to own some unrelated form.)

    Returns the disambiguated per-lemma estimate. `aggregate_loose` returns the
    undivided word-family total; the ratio between them is the "you would recognise a
    relative of this word" signal that `make_shortlist.py` scores on.

    Occurrences are summed (distinct tokens, so exact). Documents take the **max** across a
    lemma's forms rather than the sum, since summing would double-count any document holding
    two forms of the same lemma — and each form's document count is scaled by the same share
    that splits its occurrences.

    That scaling is load-bearing. Documents used to be all-or-nothing, credited only to a
    claimant winning ≥ 50% of a form, which meant a lemma that never majority-claims *any* of
    its forms accumulated occurrences and exactly zero documents:

        văz    share 0.108 of `văz`  (888 occ / 392 docs)  →  96 occ,  0 docs
        nalt   share 0.223 of `nalt` (439 occ / 300 docs)  →  98 occ,  0 docs
        soli   share 0.418 of `soli` (317 occ / 149 docs)  →  132 occ, 0 docs

    `verdict()` then reads `hist_occ >= 3 AND hist_docs >= 2`, so the docs half vetoed the occ
    half and all three came out `absent` — the verdict reserved for "no evidence either way" —
    while sitting in the relevant seam. That was 170 of the 5,780 shortlist rows with zero
    historical documents. A form seen in 392 documents whose occurrences are 10.8% this
    lemma's is evidence of roughly 42 documents, not of none; scaling says that, and keeps
    documents on the same footing as the occurrences they are compared against.
    """
    if not form_lemma:
        return dict(freqs)

    occ: dict[str, float] = {}
    doc: dict[str, float] = {}
    for word, (o, d) in freqs.items():
        lemmas = form_lemma.get(word) or [word]
        if len(lemmas) == 1:
            lemma = lemmas[0]
            occ[lemma] = occ.get(lemma, 0.0) + o
            doc[lemma] = max(doc.get(lemma, 0.0), float(d))
            continue
        # Prior: how prominent is each claimant lemma in its own right?
        weights = [freqs.get(lm, (0, 0))[0] + SHARE_ALPHA for lm in lemmas]
        total = sum(weights)
        for lemma, w in zip(lemmas, weights):
            share = w / total
            occ[lemma] = occ.get(lemma, 0.0) + o * share
            doc[lemma] = max(doc.get(lemma, 0.0), d * share)

    return {w: (int(round(v)), int(round(doc.get(w, 0.0)))) for w, v in occ.items()}


def merge_panels(*panels: dict[str, tuple[int, int]]) -> dict[str, tuple[int, int]]:
    """Combine per-lemma (occurrences, documents) from several corpora.

    Both halves are summed, and for documents that is only right *across* corpora: a
    document in Wikisource and a novel in LUMRO are different documents, so adding
    them counts each once. Within one corpus documents stay a max over the lemma's
    forms (see `aggregate_by_family`), because there the same document can hold two
    forms of the same lemma.

    Hence the order this is applied in: aggregate each corpus first, merge after.
    Merging the raw surface counts first and aggregating once would push both corpora
    through a single max and lose the documents only the smaller one contributes.
    """
    out: dict[str, tuple[int, int]] = {}
    for panel in panels:
        for lemma, (occ, doc) in panel.items():
            prev = out.get(lemma, (0, 0))
            out[lemma] = (prev[0] + occ, prev[1] + doc)
    return out


def aggregate_loose(freqs: dict[str, tuple[int, int]],
                    form_lemma: dict[str, list[str]]) -> dict[str, int]:
    """Undivided word-family totals: {lemma: occurrences}, every claimant credited in full.

    This is deliberately the *over*-counting version. Compared against the disambiguated
    figure it answers a different question — not "how often is this lemma used" but "how
    often does a reader meet something that looks like it". A large gap means the word
    survives only as a relative of a current one (`politeță` beside `politețe`), which is
    the class of entry that wastes a marker's time.
    """
    if not form_lemma:
        return {w: o for w, (o, _) in freqs.items()}
    out: dict[str, int] = {}
    for word, (o, _d) in freqs.items():
        for lemma in form_lemma.get(word) or (word,):
            out[lemma] = out.get(lemma, 0) + o
    return out


def percentile_ranks(values: dict[str, int]) -> dict[str, float]:
    """Map {word: count} → {word: percentile rank in 0..1} over the non-zero counts.

    Used instead of ppm for the historical-vs-modern comparison: a rank is scale-free,
    so a 14M-token corpus and a 17B-token one can be compared without the smaller one's
    resolution floor deciding the outcome.
    """
    present = sorted((v, w) for w, v in values.items() if v > 0)
    n = len(present)
    if n == 0:
        return {}
    return {w: (i + 1) / n for i, (_, w) in enumerate(present)}


def load_dict_meta(db_path: Path) -> dict[str, dict]:
    """Return {word: {dict_count, newest_dict_year, in_current_dict}} from dict_sources.db.

    Prefer this over `_load_dict_counts`, which re-streams the 1.65 GB dump on every run
    to recompute a number `extract_dict_sources.py` has already written down.
    """
    if not db_path.exists():
        return {}
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute('SELECT word, dict_count, newest_dict_year, '
                            'in_current_dict FROM dict_sources').fetchall()
    except sqlite3.OperationalError:
        return {}
    finally:
        conn.close()
    return {r[0]: {'dict_count': r[1], 'newest_dict_year': r[2],
                   'in_current_dict': r[3]} for r in rows}


def load_taxonomy(lexemes_db: Path) -> dict:
    """Return {word_lower: {register, domain, etymology, pos}} from Tag/ObjectTag/EntryLexeme.
    Returns empty dict with a warning if tables are absent (run extract_taxonomy.py first).

    In addition to tags under the standard register (42), domain (41), and etymology (1)
    hierarchies, captures three root-level tags that DEX applies directly to meanings:
      6  = rar          (rare usage)        → register
      17 = regional     (regional form)     → register; children = Banat, Moldova, etc.
      239 = ieșit din uz (fallen out of use) → register
    """
    conn = sqlite3.connect(lexemes_db)
    try:
        rows = conn.execute("""
            SELECT lower(l.formNoAccent), t.id, t.parentId, t.isPos, t.value
            FROM Lexeme l
            JOIN EntryLexeme el ON el.lexemeId = l.id
            JOIN TreeEntry te ON te.entryId = el.entryId
            JOIN MeaningTree m ON m.tree_id = te.treeId
            JOIN ObjectTag ot ON ot.objectId = m.meaning_id AND ot.objectType = 3
            JOIN Tag t ON t.id = ot.tagId
            WHERE t.parentId IN ({parents}) OR t.isPos = 1
               OR t.id IN ({ids})
        """.format(parents=','.join(map(str, TAG_FAMILY_BY_PARENT)),
                   ids=','.join(map(str, TAG_FAMILY_BY_ID)))).fetchall()
    except sqlite3.OperationalError:
        print("  [taxonomy] Tag/TreeEntry/MeaningTree tables not found — run extract_taxonomy.py to enable taxonomy columns")
        return {}
    finally:
        conn.close()

    taxonomy: dict = {}
    for word, tag_id, parent_id, is_pos, tag_value in rows:
        entry = taxonomy.setdefault(word, {'register': set(), 'domain': set(), 'etymology': set(), 'pos': set()})
        if is_pos:
            entry['pos'].add(tag_value)
        else:
            family = tag_family(tag_id, parent_id)   # shared with create_curated_list
            if family:
                entry[family].add(tag_value)
    return taxonomy


def verdict(hist_occ: int, hist_docs: int, modern_occ: int, rank_shift: float,
            rare_occ: int = MODERN_RARE_OCC, alive_occ: int = MODERN_ALIVE_OCC) -> str:
    """Classify a lemma from paradigm-level occurrence counts.

    Counts, not ppm — see the MODERN_* / HIST_* constants for why. All inputs are
    family-aggregated (whole paradigm), so an inflected verb is judged on its paradigm
    rather than on how often its infinitive happens to be written.

    The four verdicts a shortlisted word can carry are `extinct`, `historical_only`,
    `declining` and `absent`; `alive` and `emerging` exist so `make_shortlist.py` can
    drop them, and are never shown in the UI (see VERDICTS in public/api/_lib.php).
    """
    attested_hist = hist_occ >= HIST_MIN_OCC and hist_docs >= HIST_MIN_DOCS

    if modern_occ >= alive_occ:
        # Demonstrably in use today, whatever the history says.
        return 'emerging' if rank_shift <= -RANK_SHIFT_DECLINING else 'alive'
    if not attested_hist:
        # No historical footing, and not common now: we simply have no evidence.
        return 'absent'
    if modern_occ == 0:
        return 'extinct'
    if modern_occ < rare_occ:
        return 'historical_only'
    return 'declining'


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Diachronic comparison: Wikisource vs CulturaX frequency ratio.')
    parser.add_argument('--all-dex', action='store_true',
                        help='Include all DEX words (default: curated candidates only)')
    parser.add_argument('--smoothing', type=float, default=SMOOTHING,
                        help=f'Per-million smoothing for log ratio (default: {SMOOTHING})')
    parser.add_argument('-o', '--output', type=Path, default=OUTPUT_CSV)
    parser.add_argument('--top', type=int, default=20,
                        help='Print top N historically-skewed words in summary')
    args = parser.parse_args()

    for p, label in [(LEXEMES_DB, 'lexemes.db'), (FREQ_DB, 'corpus_frequencies.db')]:
        if not p.exists():
            print(f'Missing: {p}  — run the Phase 1 and corpus pipeline first.')
            return 1

    freq_conn = sqlite3.connect(FREQ_DB)

    ws_tokens     = get_corpus_tokens(freq_conn, HIST_CORPUS)
    lumro_tokens  = get_corpus_tokens(freq_conn, LUMRO_CORPUS)
    hist_tokens   = ws_tokens + lumro_tokens
    cx_tokens     = get_corpus_tokens(freq_conn, MODERN_CORPUS)
    corola_tokens = get_corpus_tokens(freq_conn, COROLA_CORPUS)   # reported, not counted
    modern_tokens = sum(get_corpus_tokens(freq_conn, c) for c in MODERN_CORPORA)

    if hist_tokens == 0 and modern_tokens == 0:
        print('No completed corpus runs found in corpus_frequencies.db.')
        print(f'  Run process_wikisource.py and/or process_culturax.py first.')
        freq_conn.close()
        return 1

    print(f'Corpus sizes:')
    subtitle_tokens = get_corpus_tokens(freq_conn, SUBTITLE_CORPUS)

    if ws_tokens:
        print(f'  {HIST_CORPUS:<20} {ws_tokens:>15,} tokens')
    else:
        print(f'  {HIST_CORPUS:<20}  (no completed run)')
    if lumro_tokens:
        print(f'  {LUMRO_CORPUS:<20} {lumro_tokens:>15,} tokens')
    else:
        print(f'  {LUMRO_CORPUS:<20}  (no completed run — process_lumro.py)')
    if cx_tokens:
        print(f'  {MODERN_CORPUS:<20} {cx_tokens:>15,} tokens')
    else:
        print(f'  {MODERN_CORPUS:<20}  (no completed run)')
    if corola_tokens:
        print(f'  {COROLA_CORPUS:<20} {corola_tokens:>15,} tokens  '
              f'(loaded, NOT in the modern panel — spans 1945+, see MODERN_CORPORA)')
    if subtitle_tokens:
        print(f'  {SUBTITLE_CORPUS:<20} {subtitle_tokens:>15,} tokens')
    else:
        print(f'  {SUBTITLE_CORPUS:<20}  (no completed run)')

    curated_only = not args.all_dex
    print(f'\nLoading DEX candidates ({"curated list" if curated_only else "all DEX"})...')
    try:
        candidates = load_dex_candidates(LEXEMES_DB, curated_only, CURATED_CSV)
    except FileNotFoundError as e:
        print(e)
        return 1
    print(f'  {len(candidates):,} words')

    print('Loading corpus frequencies...')
    ws_freqs       = load_corpus_freqs(freq_conn, HIST_CORPUS)     if ws_tokens       else {}
    lumro_freqs    = load_corpus_freqs(freq_conn, LUMRO_CORPUS)    if lumro_tokens    else {}
    cx_freqs       = load_corpus_freqs(freq_conn, MODERN_CORPUS)   if cx_tokens       else {}
    subtitle_freqs = load_corpus_freqs(freq_conn, SUBTITLE_CORPUS) if subtitle_tokens else {}
    freq_conn.close()

    def _sum_forms(*panels):
        """Citation-form view of a whole panel, for the diffable raw columns."""
        out: dict[str, tuple[int, int]] = {}
        for panel in panels:
            for w, (o, d) in panel.items():
                prev = out.get(w, (0, 0))
                out[w] = (prev[0] + o, prev[1] + d)
        return out

    hist_freqs   = _sum_forms(ws_freqs, lumro_freqs)
    modern_freqs = _sum_forms(cx_freqs)

    print('Loading DEX taxonomy...')
    taxonomy = load_taxonomy(LEXEMES_DB)
    print(f'  {len(taxonomy):,} words with taxonomy tags')

    print('Loading definition index...')
    def_words = _load_definition_words(DEFINITIONS_DB)
    print(f'  {len(def_words):,} words with definitions')

    print('Loading dictionary coverage...')
    dict_meta = load_dict_meta(DICT_SOURCES_DB)
    if dict_meta:
        print(f'  {len(dict_meta):,} headwords from {DICT_SOURCES_DB}')
    else:
        # Fall back to re-streaming the dump; slower, and yields no year data.
        print(f'  {DICT_SOURCES_DB} not found — falling back to the dump '
              f'(run extract_dict_sources.py to skip this)')
        dict_meta = {w: {'dict_count': c, 'newest_dict_year': None,
                         'in_current_dict': None}
                     for w, c in _load_dict_counts(DEX_SQL_PATH).items()}
        print(f'  {len(dict_meta):,} headwords across all dictionaries')

    print('Loading inflected-form paradigms...')
    form_lemma = load_form_lemma_map(INFLECTED_DB)
    print(f'  {len(form_lemma):,} surface forms mapped to lemmas')

    print('Aggregating corpus counts over paradigms...')
    # Each historical corpus is aggregated on its own and the results merged — see
    # merge_panels for why that order matters to the document counts.
    hist_fam     = merge_panels(aggregate_by_family(ws_freqs,    form_lemma),
                                aggregate_by_family(lumro_freqs, form_lemma))
    modern_fam   = aggregate_by_family(cx_freqs, form_lemma)
    subtitle_fam = aggregate_by_family(subtitle_freqs, form_lemma)
    modern_loose = aggregate_loose(modern_freqs, form_lemma)
    print(f'  {len(hist_fam):,} historical / {len(modern_fam):,} modern lemmas')

    hist_rank   = percentile_ranks({w: o for w, (o, _) in hist_fam.items()})
    modern_rank = percentile_ranks({w: o for w, (o, _) in modern_fam.items()})

    # Restrict to candidates that appear in at least one corpus (unless --all-dex)
    if args.all_dex:
        universe = candidates.keys() | hist_freqs.keys() | modern_freqs.keys()
    else:
        universe = candidates.keys()

    rare_occ, alive_occ = scaled_modern_thresholds(modern_tokens)
    if (rare_occ, alive_occ) != (MODERN_RARE_OCC, MODERN_ALIVE_OCC):
        print(f'Modern thresholds rescaled to panel size '
              f'({modern_tokens / CALIBRATION_MODERN_TOKENS:.3f}× the calibration corpus): '
              f'rare {MODERN_RARE_OCC} → {rare_occ}, alive {MODERN_ALIVE_OCC} → {alive_occ}')

    S = args.smoothing
    hist_scale     = 1_000_000 / hist_tokens     if hist_tokens     else 0.0
    modern_scale   = 1_000_000 / modern_tokens   if modern_tokens   else 0.0
    subtitle_scale = 1_000_000 / subtitle_tokens if subtitle_tokens else 0.0

    results = []
    for word in universe:
        meta = candidates.get(word, {'dex_frequency': 0.0, 'description': '', 'rarity_category': ''})

        # Citation-form counts, kept so the rescore can be diffed against the old data.
        h_occ, h_doc = hist_freqs.get(word,     (0, 0))
        m_occ, m_doc = modern_freqs.get(word,   (0, 0))
        s_occ, s_doc = subtitle_freqs.get(word, (0, 0))

        # Paradigm-level counts — what the verdict is actually computed from.
        hf_occ, hf_doc = hist_fam.get(word,     (0, 0))
        mf_occ, mf_doc = modern_fam.get(word,   (0, 0))
        sf_occ, _      = subtitle_fam.get(word, (0, 0))

        hist_ppm     = h_occ * hist_scale     if hist_scale     else 0.0
        modern_ppm   = m_occ * modern_scale   if modern_scale   else 0.0
        subtitle_ppm = s_occ * subtitle_scale if subtitle_scale else 0.0

        log_ratio  = math.log2((hist_ppm + S) / (modern_ppm + S))
        rank_shift = hist_rank.get(word, 0.0) - modern_rank.get(word, 0.0)

        # How much bigger the undivided word family is than this lemma alone. High values
        # mean the word survives only as a relative of a current one — `tinereță` 298×
        # beside `tinerețe`, `veșcă` 938× beside `veste` — while a genuinely isolated rare
        # word sits at 1×. This is what flags archaic variants of live vocabulary.
        ml_occ = modern_loose.get(word, 0)
        family_ratio = ml_occ / mf_occ if mf_occ else 1.0

        dmeta = dict_meta.get(word) or {}
        tax = taxonomy.get(word, {})
        results.append({
            'word':               word,
            'dex_frequency':      f"{meta['dex_frequency']:.4f}",
            'description':        meta['description'],
            'rarity_category':    meta['rarity_category'],
            'hist_occurrences':   h_occ,
            'hist_documents':     h_doc,
            'hist_ppm':           f'{hist_ppm:.4f}',
            'modern_occurrences': m_occ,
            'modern_documents':   m_doc,
            'modern_ppm':         f'{modern_ppm:.4f}',
            'subtitle_occurrences': s_occ,
            'subtitle_documents':   s_doc,
            'subtitle_ppm':         f'{subtitle_ppm:.4f}',
            'hist_occ':           hf_occ,
            'hist_docs':          hf_doc,
            'modern_occ':         mf_occ,
            'modern_docs':        mf_doc,
            'subtitle_occ':       sf_occ,
            'modern_occ_loose':   ml_occ,
            'family_ratio':       f'{family_ratio:.2f}',
            'hist_rank':          f'{hist_rank.get(word, 0.0):.4f}',
            'modern_rank':        f'{modern_rank.get(word, 0.0):.4f}',
            'rank_shift':         f'{rank_shift:.4f}',
            'log_ratio':          f'{log_ratio:.4f}',
            'verdict':            verdict(hf_occ, hf_doc, mf_occ, rank_shift,
                                           rare_occ, alive_occ),
            'dex_pos':            '|'.join(sorted(tax.get('pos',       set()))),
            'dex_register':       '|'.join(sorted(tax.get('register',  set()))),
            'dex_domain':         '|'.join(sorted(tax.get('domain',    set()))),
            'dex_etymology':      '|'.join(sorted(tax.get('etymology', set()))),
            'has_definition':     1 if word in def_words else 0,
            'dict_count':         dmeta.get('dict_count', 0),
            'newest_dict_year':   dmeta.get('newest_dict_year') or '',
            'in_current_dict':    dmeta.get('in_current_dict') if dmeta.get('in_current_dict') is not None else '',
        })

    results.sort(key=lambda r: float(r['rank_shift']), reverse=True)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        'word', 'dex_frequency', 'description', 'rarity_category',
        'hist_occurrences', 'hist_documents', 'hist_ppm',
        'modern_occurrences', 'modern_documents', 'modern_ppm',
        'subtitle_occurrences', 'subtitle_documents', 'subtitle_ppm',
        'hist_occ', 'hist_docs', 'modern_occ', 'modern_docs', 'subtitle_occ',
        'modern_occ_loose', 'family_ratio',
        'hist_rank', 'modern_rank', 'rank_shift',
        'log_ratio', 'verdict',
        'dex_pos', 'dex_register', 'dex_domain', 'dex_etymology',
        'has_definition', 'dict_count', 'newest_dict_year', 'in_current_dict',
    ]
    with args.output.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(results)

    print(f'\nWrote {len(results):,} rows → {args.output}')

    # Verdict summary
    from collections import Counter
    counts = Counter(r['verdict'] for r in results)
    print('\nVerdict breakdown:')
    for v in ('extinct', 'historical_only', 'declining', 'absent',
              'alive', 'emerging'):
        n = counts.get(v, 0)
        if n:
            print(f'  {v:<20} {n:>6,}')

    # Top N most historically-skewed (results are already sorted by rank_shift)
    top = [r for r in results if int(r['hist_occ']) > 0][:args.top]
    if top:
        print(f'\nTop {len(top)} historically-skewed (highest rank_shift, hist_occ > 0):')
        print(f'  {"word":<22} {"rank_shift":>10} {"hist_occ":>9} {"modern_occ":>11}  verdict')
        for r in top:
            print(f'  {r["word"]:<22} {float(r["rank_shift"]):>10.2f} '
                  f'{int(r["hist_occ"]):>9,} {int(r["modern_occ"]):>11,}  {r["verdict"]}')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
