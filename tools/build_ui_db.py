#!/usr/bin/env python3
"""Build public/data/ui.db from pipeline CSV outputs + definitions.db.

Run from repo root:
    python tools/build_ui_db.py

The build is all-or-nothing. It writes a candidate database to a unique temporary file
beside the output, validates it, and replaces the output with one atomic `os.replace`.
A failure at any step leaves the previous output untouched. See `build()` and
`docs/ui-db-build.md` for the input policy, locking and ID-registry failure rules.
"""
import argparse
import contextlib
import csv
import dataclasses
import fcntl
import os
import re
import sqlite3
import sys
import tempfile
from collections import Counter
from pathlib import Path

try:
    from wordfreq import zipf_frequency as _zipf
except ImportError:
    _zipf = None

sys.path.insert(0, str(Path(__file__).parent))
import word_ids as _word_ids
from word_ids import apply_to_db as _apply_word_ids
from editorial import apply_to_db as _apply_editorial, EDITORIAL_PATH

# The modern-usage bands are the pipeline's own thresholds, not new numbers — imported
# rather than copied so that rescaling stays in one place. See mark_modern_band().
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from validate_diachronic import (  # noqa: E402
    MODERN_CORPORA as _MODERN_CORPORA,
    get_corpus_tokens as _corpus_tokens,
    scaled_modern_thresholds as _scaled_modern_thresholds,
)
# The canonical Romanian normalization (lower → cedilla-to-comma → NFC). Lexeme forms
# come out of the dump with their original case, so `Octomvre` has to fold onto
# `octomvre` before it can be matched against a shortlist word. See mark_dex_variants().
from dump_parser import normalize  # noqa: E402

SHORTLIST_PATH  = Path('data/processed/forgotten_words_shortlist.csv')
RARE_PATH       = Path('data/processed/rare_words_wordfreq.csv')
WEB_PATH        = Path('data/processed/diachronic_shortlist_web_validated.csv')
DEFINITIONS_PATH = Path('data/processed/definitions.db')
DICT_SOURCES_PATH = Path('data/processed/dict_sources.db')
SYNONYMS_PATH     = Path('data/processed/synonyms.db')
MEANINGS_PATH     = Path('data/processed/meanings.db')
LEXEMES_PATH      = Path('data/processed/lexemes.db')
FREQ_PATH         = Path('data/processed/corpus_frequencies.db')
INFLECTED_PATH    = Path('data/processed/inflected_forms.db')
OUT_PATH        = Path('public/data/ui.db')

# A production build holds ~18k words. Below this, `build()` refuses to publish unless the
# caller passes a lower `min_words` (tests do; the CLI has `--min-words`).
MIN_WORDS_DEFAULT = 10_000
# A candidate smaller than this share of the previous output is refused (a truncated
# shortlist would otherwise replace a good database). `allow_shrink=True` overrides.
SHRINK_FLOOR = 0.5

_ETYM_JUNK = {'vezi', 'cf.', 'după', 'după unii', 'probabil', 'cuvânt',
              'necunoscută', 'de la', 'sau'}


def _float(v):
    try:
        return float(v) if v not in ('', None) else None
    except ValueError:
        return None


def _int(v):
    try:
        return int(v) if v not in ('', None) else None
    except ValueError:
        return None


def _bool(v):
    if v in ('true', 'True', '1'):
        return 1
    if v in ('false', 'False', '0'):
        return 0
    return None


def _normalize_sep(val):
    if not val:
        return None
    return val.replace('; ', '|').replace(';', '|')


_DIACRITIC_MAP = str.maketrans('țșţşăâî', 'tstsaai')

# ── Part of speech ───────────────────────────────────────────────────────────────
#
# `dex_pos` used to come only from meaning-level taxonomy tags, which covered 2.9% of
# the list and were wrong when they did fire: `visternic` (modelType M, masculine) came
# out as "substantiv feminin", because the DEX entry also covers the feminine form
# `vistiernică` and the tag bled across. With coverage that low the POS filter matched
# almost nothing — picking `vb.` returned zero words.
#
# `Lexeme.modelType` is the inflection model DEX actually conjugates the word with. It is
# present on all 317,721 lexemes and says what the word *is*, so it is the primary source
# now; taxonomy tags are kept only for things a model cannot express (locuțiuni, simbol).
# Mapping verified by sampling high-frequency words in each class.
_MODEL_POS = {
    'F':  'substantiv feminin',
    'M':  'substantiv masculin',
    'N':  'substantiv neutru',
    'A':  'adjectiv', 'AF': 'adjectiv', 'AM': 'adjectiv', 'AN': 'adjectiv',
    'V':  'verb',     'VT': 'verb',     'VI': 'verb',
    'PT': 'participiu',
    'P':  'pronume',
    'SP': 'nume propriu',
}

# 'T' (strămoși, cii, eți) and 'IL' (contrare, militare) are inflected forms rather than
# headwords, and 'I' means "invariable" — for those, only `description` says anything.
_DESC_POS = {
    'adv.':    'adverb',
    'interj.': 'interjecție',
    'adj.':    'adjectiv',
    'prep.':   'prepoziție',
    'conj.':   'conjuncție',
    'pron.':   'pronume',
    's.f.':    'substantiv feminin',
    's.m.':    'substantiv masculin',
    's.n.':    'substantiv neutru',
    'vb.':     'verb',
    'part.':   'participiu',
}


def _pos_from_lexeme(model_type: str | None, description: str | None) -> str | None:
    """POS for one lexeme row, preferring the inflection model over the description."""
    pos = _MODEL_POS.get((model_type or '').strip())
    if pos:
        return pos
    return _DESC_POS.get((description or '').strip().lower())


def load_pos_from_lexemes(lexemes_db: Path) -> dict[str, set[str]]:
    """{normalized headword: {pos, ...}} — a word can legitimately have several.

    `abate` is both a masculine noun (the abbot) and a verb, as two separate lexemes;
    both belong on the word.
    """
    if not lexemes_db.exists():
        return {}
    conn = sqlite3.connect(str(lexemes_db))
    out: dict[str, set[str]] = {}
    for form, model_type, description in conn.execute(
            'SELECT formNoAccent, modelType, description FROM Lexeme '
            " WHERE formNoAccent IS NOT NULL AND formNoAccent != ''"):
        pos = _pos_from_lexeme(model_type, description)
        if pos:
            out.setdefault(form.lower(), set()).add(pos)
    conn.close()
    return out


def _strip_diacritics(s: str) -> str:
    return s.lower().translate(_DIACRITIC_MAP)


def merge_dict_sources(conn: sqlite3.Connection, sources_db: Path) -> None:
    """Populate words.sources (pipe-delimited dictionary names) from dict_sources.db.

    Matches on the exact headword first; for the ~2% of UI words with no exact
    headword (mostly feminine / inflected forms), falls back to a diacritic-stripped
    match — but only when that normalized form maps to a single dict_sources entry,
    to avoid pulling in the wrong headword's dictionary list.
    """
    if not sources_db.exists():
        print(f'  (dict sources DB not found, skipping: {sources_db})')
        return
    print(f'Merging dictionary sources from {sources_db}…')
    sconn = sqlite3.connect(str(sources_db))
    exact: dict[str, str] = {}
    norm_index: dict[str, str] = {}
    norm_dupes: set[str] = set()
    for word, srcs in sconn.execute('SELECT word, sources FROM dict_sources'):
        if not word or not srcs:
            continue
        exact[word] = srcs
        n = _strip_diacritics(word)
        if n in norm_index:
            norm_dupes.add(n)
        else:
            norm_index[n] = srcs
    sconn.close()

    updated = 0
    for (w,) in conn.execute('SELECT word FROM words').fetchall():
        srcs = exact.get(w)
        if srcs is None:
            n = _strip_diacritics(w)
            if n not in norm_dupes:
                srcs = norm_index.get(n)
        if srcs is not None:
            conn.execute('UPDATE words SET sources=? WHERE word=?', (srcs, w))
            updated += 1
    print(f'  {updated} words matched to dictionary sources')


def merge_synonyms(conn: sqlite3.Connection, syn_db: Path) -> None:
    """Populate words.synonyms / words.antonyms from synonyms.db (scrape_synonyms.py).

    Optional: the app renders the slot only when a word has data, so a partial scrape is
    fine and the page simply omits the section for words not reached yet.
    """
    if not syn_db.exists():
        print(f'  (synonyms DB not found, skipping: {syn_db})')
        return
    print(f'Merging synonyms from {syn_db}…')
    sconn = sqlite3.connect(str(syn_db))
    try:
        rows = sconn.execute(
            'SELECT word, synonyms, antonyms FROM synonyms').fetchall()
    except sqlite3.OperationalError:
        print('  (no synonyms table yet)')
        return
    finally:
        sconn.close()
    n = 0
    for word, syns, ants in rows:
        cur = conn.execute(
            'UPDATE words SET synonyms = ?, antonyms = ? WHERE word = ?',
            (syns or None, ants or None, word))
        n += cur.rowcount
    print(f'  {n:,} words given synonyms/antonyms')


# ── Senses ───────────────────────────────────────────────────────────────────────
#
# extract_meanings.py writes a faithful copy of every `Meaning` row belonging to a
# shortlist word's Tree(s) — senses, sub-senses, citations, etymology, comments,
# compounds and expressions, empty text included. merge_senses() below is the one place
# that turns that raw tree into what the UI renders: it drops empty-text senses (keeping
# their sub-senses and re-attaching their citations to the nearest non-empty ancestor),
# orders senses by breadcrumb rather than by id, and merges the rare word with two Tree
# rows into one numbering. See docs/senses-plan.md §5 for the full derivation.

def bc_key(bc: str) -> tuple[int, ...]:
    """Parse a breadcrumb ('1.', '1.1.', '10.') into a sortable tuple of ints.

    Sorting the breadcrumb as text puts '10.' between '1.' and '2.' — this is the one
    case a string sort gets wrong, and every `type=0` row in the dump has a non-empty,
    all-numeric breadcrumb (verified, 0 exceptions), so `parentId` is not needed for
    ordering senses at all.
    """
    return tuple(int(p) for p in bc.strip('.').split('.') if p.isdigit())


def _process_sense_tree(rows: list[tuple],
                         synonyms_by_meaning: dict[int, list[str]] | None = None) -> list[dict]:
    """Turn one Tree's raw Meaning rows into ordered sense/compound/expression units.

    `rows` are (meaning_id, word, tree_id, parent_id, type, breadcrumb, display_order,
    text) tuples, all sharing one tree_id. Returns units in display order: senses
    (type=0) first, sorted by bc_key(breadcrumb); compounds/expressions (type=4/5) after,
    sorted by display_order — their breadcrumb is always empty, so bc_key cannot order
    them and dexonline's own display_order is what is left.

    `synonyms_by_meaning` is `extract_meanings.py`'s `meaning_synonyms` table (a
    `Relation.type=1` fallback — see its module docstring): a sense DEX gives no free
    text keeps its own numbered slot if it has synonyms, rather than being dropped like
    a genuinely empty placeholder. `zăticni` sense '1.' is the case that motivated this
    — empty `internalRep`, 9 synonym relations, and dexonline's own page renders that
    exact list as the sense's "definition". Citations reattach through the same
    mechanism: a sense kept alive only by its synonyms is still a valid reattachment
    target for `resolve_target()`.
    """
    synonyms_by_meaning = synonyms_by_meaning or {}
    by_id = {r[0]: r for r in rows}

    citations_by_parent: dict[int, list[str]] = {}
    for r in rows:
        if r[4] == 2 and r[7]:
            citations_by_parent.setdefault(r[3], []).append(r[7])

    def has_content(node: tuple) -> bool:
        return bool(node[7]) or bool(synonyms_by_meaning.get(node[0]))

    def resolve_target(parent_id: int) -> int | None:
        # Climbs the parentId chain from a citation's immediate parent until it finds a
        # node this pass will actually emit (a non-empty sense/compound/expression), or
        # runs out of tree to climb — an orphaned quote is dropped rather than attached
        # to the word as a whole, which would read as evidence for the wrong meaning.
        cur = parent_id
        seen: set[int] = set()
        while cur != 0 and cur not in seen and cur in by_id:
            seen.add(cur)
            node = by_id[cur]
            if node[4] in (0, 4, 5) and has_content(node):
                return cur
            cur = node[3]
        return None

    resolved_citations: dict[int, list[str]] = {}
    for parent_id, texts in citations_by_parent.items():
        target = resolve_target(parent_id)
        if target is not None:
            resolved_citations.setdefault(target, []).extend(texts)

    senses = sorted((r for r in rows if r[4] == 0 and has_content(r)), key=lambda r: bc_key(r[5]))
    extras = sorted((r for r in rows if r[4] in (4, 5) and has_content(r)),
                     key=lambda r: (r[6], r[0]))

    units: list[dict] = []
    for r in senses:
        units.append({
            'meaning_id': r[0], 'kind': 'sense', 'breadcrumb': r[5],
            'depth': len(bc_key(r[5])), 'text': r[7],
            'citations': resolved_citations.get(r[0], []),
            'synonyms': synonyms_by_meaning.get(r[0], []),
        })
    for r in extras:
        units.append({
            'meaning_id': r[0], 'kind': 'compound' if r[4] == 4 else 'expression',
            'breadcrumb': '', 'depth': 1, 'text': r[7],
            'citations': resolved_citations.get(r[0], []),
            'synonyms': synonyms_by_meaning.get(r[0], []),
        })
    return units


def merge_senses(conn: sqlite3.Connection, meanings_db: Path) -> None:
    """Populate senses / sense_citations / words.dex_etymon from meanings.db.

    Idempotent — clears both tables (and dex_etymon) before repopulating, so a second
    run of a migration produces a byte-identical file. Optional, like every other merge
    in this file: a build must succeed without meanings.db, since not every checkout has
    run extract_meanings.py.
    """
    if not meanings_db.exists():
        print(f'  (meanings DB not found, skipping: {meanings_db})')
        return
    print(f'Merging senses from {meanings_db}…')

    mconn = sqlite3.connect(f'file:{meanings_db}?mode=ro', uri=True)
    try:
        meaning_rows = mconn.execute(
            'SELECT meaning_id, word, tree_id, parent_id, type, breadcrumb, '
            '       display_order, text '
            'FROM meanings ORDER BY word, tree_id, display_order, meaning_id').fetchall()
        tag_rows = mconn.execute('SELECT meaning_id, tag FROM meaning_tags').fetchall()
    except sqlite3.OperationalError:
        print('  (meanings DB missing expected tables, skipping)')
        mconn.close()
        return
    # Separate try/except: meaning_synonyms is newer than meanings/meaning_tags, so a
    # meanings.db built before extract_meanings.py grew the Relation pass still merges
    # senses fine — just without the empty-text synonym fallback, same as before.
    try:
        synonym_rows = mconn.execute(
            'SELECT meaning_id, ord, word FROM meaning_synonyms').fetchall()
    except sqlite3.OperationalError:
        synonym_rows = []
    mconn.close()

    tags_by_meaning: dict[int, list[str]] = {}
    for mid, tag in tag_rows:
        tags_by_meaning.setdefault(mid, []).append(tag)

    synonyms_by_meaning: dict[int, list[str]] = {}
    for mid, ord_, word in sorted(synonym_rows, key=lambda r: (r[0], r[1])):
        synonyms_by_meaning.setdefault(mid, []).append(word)

    by_word: dict[str, list[tuple]] = {}
    for row in meaning_rows:
        by_word.setdefault(row[1], []).append(row)

    conn.execute('DELETE FROM senses')
    conn.execute('DELETE FROM sense_citations')
    conn.execute('UPDATE words SET dex_etymon = NULL')

    sense_rows: list[tuple] = []
    citation_rows: list[tuple] = []
    etymon_updates: list[tuple] = []
    homonym_words = 0
    depth2plus = 0
    text_empty_synonym_only = 0

    for word, rows in by_word.items():
        tree_ids = sorted({r[2] for r in rows})

        word_units: list[dict] = []
        trees_with_units = 0
        for tid in tree_ids:
            units = _process_sense_tree([r for r in rows if r[2] == tid], synonyms_by_meaning)
            if units:
                trees_with_units += 1
            word_units.extend(units)
        if trees_with_units > 1:
            homonym_words += 1

        # Etymology is word-level, not sense-level, and collected across every tree —
        # `type=1` rows hang off the tree root. Order of first appearance, deduplicated:
        # a word rarely has more than one, but a homonym's second tree could repeat it.
        etymons: list[str] = []
        for r in rows:
            if r[4] == 1 and r[7] and r[7] not in etymons:
                etymons.append(r[7])
        if etymons:
            etymon_updates.append(('|'.join(etymons), word))

        for ord_, u in enumerate(word_units):
            if u['depth'] >= 2:
                depth2plus += 1
            if not u['text'] and u['synonyms']:
                text_empty_synonym_only += 1
            tag_list = sorted(set(tags_by_meaning.get(u['meaning_id'], [])))
            sense_rows.append((
                word, ord_, u['breadcrumb'], u['depth'], u['kind'], u['text'],
                '|'.join(tag_list) if tag_list else None,
                '|'.join(u['synonyms']) if u['synonyms'] else None,
            ))
            for cord, ctext in enumerate(u['citations']):
                citation_rows.append((word, ord_, cord, ctext))

    conn.executemany(
        'INSERT INTO senses (word, ord, breadcrumb, depth, kind, text, tags, synonyms) '
        'VALUES (?,?,?,?,?,?,?,?)', sense_rows)
    conn.executemany(
        'INSERT INTO sense_citations (word, sense_ord, ord, text) VALUES (?,?,?,?)',
        citation_rows)
    conn.executemany('UPDATE words SET dex_etymon = ? WHERE word = ?', etymon_updates)

    words_with_senses = len({r[0] for r in sense_rows})
    print(f'  {len(sense_rows):,} sense/compound/expression rows '
          f'({words_with_senses:,} words), {len(citation_rows):,} citations, '
          f'{len(etymon_updates):,} etymons — {homonym_words} words merged two trees '
          f'({depth2plus:,} sub-senses at depth ≥2, {text_empty_synonym_only:,} '
          f'kept text-empty via the synonym fallback)')


# ── Diminutives ──────────────────────────────────────────────────────────────────
#
# Two independent signals, unioned. Neither is complete on its own and both are kept
# deliberately narrow, because the flag drives a hide-toggle: a false positive costs a
# real word the moment someone switches it on.
#
# 1. DEX says so. The definition opens with "Diminutiv al lui X" — the dictionary's own
#    statement, and the only signal that survives a phonetic alternation the spelling
#    hides (`vătășel` → `vătaf`, `cărucioară` → `căruță`). Matched at the start of a
#    meaning (the string start, or just after a `|` separator) and allowing one short
#    parenthetical, so `(Ca termen de adresare) Diminutiv al lui văr` counts. What it
#    must *not* match is a quotation that merely uses the word: `alintare` carries
#    "Țîțacă e diminutiv, adică alintare a vorbei țață", which is about another word
#    entirely — hence the required "al/a/ale/lui/de la" right after.
#
# 2. Unambiguous suffix + a base DEX knows. `-uleț -uliță -ișor -ișoară -cioară -uț -uță
#    -șor -șoară`, and only when stripping the suffix (restoring a final `ă` for the
#    feminine ones) lands on a real lexeme: `noruleț` → `nor`, `mescioară` → `mesă`.
#    The suffixes left out are the productive-but-ambiguous ones: `-iță` is as often a
#    feminine agent (`păstoriță`, `boieriță`, `vorniciță`) as a diminutive, and `-ic`,
#    `-ică`, `-el`, `-ea`, `-aș` pull in `semitic`, `mastică`, `solemnel`, `livrea`,
#    `birtaș`. Together they added ~340 words at maybe half precision, which is the
#    wrong trade for a filter people turn on to *stop* seeing things.
#
# On the current build: 345 from the definitions, 58 more from the suffixes, 403 total.
_DIMINUTIVE_DEF_RE = re.compile(
    r'(?:^|\|)\s*(?:\([^)]{0,40}\)\s*)?[Dd]iminutiv\w*\s+(?:al|a|ale|lui|de\s+la)\b'
)

# suffix → the endings to try on the stem when looking the base form up
_DIMINUTIVE_SUFFIXES = {
    'uleț':   ('',),
    'uliță':  ('ă',),
    'ișor':   ('',),
    'ișoară': ('ă',),
    'cioară': ('ă',),
    'șoară':  ('ă',),
    'șor':    ('',),
    'uță':    ('ă',),
    'uț':     ('',),
}


def _diminutive_by_suffix(word: str, forms: set[str]) -> bool:
    for suffix, endings in _DIMINUTIVE_SUFFIXES.items():
        # +2: a stem shorter than that is not a word the suffix was added to.
        if not word.endswith(suffix) or len(word) <= len(suffix) + 2:
            continue
        stem = word[:-len(suffix)]
        for ending in endings:
            base = stem + ending
            if base != word and base in forms:
                return True
    return False


def build_vocab_table(conn: sqlite3.Connection, kinds: set[str] | None = None) -> None:
    """(Re)populate the `vocab` table that drives the filter-sheet dropdowns.

    `kinds` restricts the rebuild to a subset (e.g. {'register'}) so a migration can
    refresh one dropdown's options on an existing ui.db without touching the others.
    Idempotent either way: each kind's rows are cleared before being recomputed, so
    re-running never duplicates or leaves stale values behind.
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS vocab (
            kind  TEXT,
            value TEXT,
            count INTEGER
        )
    """)

    for kind, col, exclude in [
        ('register',  'dex_register',  None),
        ('domain',    'dex_domain',    None),
        ('etymology', 'dex_etymology', _ETYM_JUNK),
        ('pos',       'dex_pos',       None),
    ]:
        if kinds is not None and kind not in kinds:
            continue
        conn.execute('DELETE FROM vocab WHERE kind = ?', (kind,))
        rows = conn.execute(
            f'SELECT {col} FROM words WHERE {col} IS NOT NULL'
        ).fetchall()
        counts: Counter = Counter()
        for (v,) in rows:
            for part in v.split('|'):
                p = part.strip()
                if p and (exclude is None or p not in exclude):
                    counts[p] += 1
        for value, count in counts.most_common():
            conn.execute(
                'INSERT INTO vocab (kind, value, count) VALUES (?,?,?)',
                (kind, value, count),
            )


def mark_diminutives(conn: sqlite3.Connection, lexemes_db: Path) -> None:
    """Populate words.diminutive_like. Idempotent; safe to re-run."""
    print('Marking diminutives…')
    forms: set[str] = set()
    if lexemes_db.exists():
        lconn = sqlite3.connect(str(lexemes_db))
        forms = {
            f.lower() for (f,) in lconn.execute(
                'SELECT formNoAccent FROM Lexeme '
                " WHERE formNoAccent IS NOT NULL AND formNoAccent != ''")
        }
        lconn.close()
    else:
        print(f'  (lexemes.db not found, suffix rule skipped: {lexemes_db})')

    conn.execute('UPDATE words SET diminutive_like = 0')
    by_def = by_suffix = 0
    marked = []
    for word, definition in conn.execute('SELECT word, definition FROM words').fetchall():
        hit_def = bool(definition) and _DIMINUTIVE_DEF_RE.search(definition) is not None
        hit_suf = bool(forms) and _diminutive_by_suffix(word.lower(), forms)
        if hit_def:
            by_def += 1
        if hit_suf and not hit_def:
            by_suffix += 1
        if hit_def or hit_suf:
            marked.append((word,))
    conn.executemany('UPDATE words SET diminutive_like = 1 WHERE word = ?', marked)
    print(f'  {len(marked):,} diminutives '
          f'({by_def:,} stated in the definition, {by_suffix:,} more by suffix)')


# ── Archaic spellings ────────────────────────────────────────────────────────────
#
# A word can be on this list only because its *spelling* was modernized while the word
# itself is thoroughly alive: `situațiune` is not forgotten Romanian, it is how people
# wrote `situație` before the twentieth century tidied it up. `variant_like` cannot see
# these — it keys on a shared inflectional paradigm, and `strein`/`străin` have different
# stems — so they sit in the default view looking like finds.
#
# **These rules are deliberately narrow, and the narrowness is the design.** A flag that
# hides is asymmetric: a false negative leaves things as they are, a false positive
# removes a real word from the only view most people will ever look at, and nothing
# surfaces it again. That is how `proper_noun_like` once hid `gheb`.
#
# Measured precision per rule over the built list (twin found / rule fires), which is why
# the tempting general rules are absent:
#
#     -țiune → -ție          313 fires, 298 twins (95%)   kept
#     sb/sd/sg → zb/zd/zg     26 fires,  26 twins (100%)  kept
#     des+voiced → dez        26 fires,  24 twins (92%)   kept
#     -ziune/-siune           34 fires,  25 twins (74%)   kept
#     adv → av                 5 fires,   3 twins         kept
#     -ea → -a               209 fires,  25 twins (12%)   REJECTED — pavea→pava,
#                                                         zaharea→zahara are real words
#     e → ă (1st syll)     2,300 fires,  69 twins (3%)    REJECTED — peți→păți are
#                                                         different words entirely
#     iu → i               1,037 fires,  88 twins (8%)    REJECTED — albiu→albi likewise
#     o → u (1st syll)     1,984 fires, 124 twins (6%)    REJECTED — right answers
#                                                         (coprins→cuprins) buried in noise
#
# Every rule must also clear TWIN_RATIO: the modern form has to be overwhelmingly more
# common in the modern corpus, so a pair that is merely two live spellings stays visible.
_SPELLING_RULES = [
    (re.compile(r'țiune$'), 'ție'),
    (re.compile(r'ziune$'), 'zie'),
    (re.compile(r'siune$'), 'sie'),
    (re.compile(r'^s(?=[bdg])'), 'z'),
    (re.compile(r'^des(?=[bdgjlmnrv])'), 'dez'),
    (re.compile(r'^adv'), 'av'),
]
TWIN_RATIO = 20


def mark_archaic_spellings(conn: sqlite3.Connection, freq_db: Path) -> None:
    """Populate words.archaic_spelling / words.spelling_of. Idempotent."""
    print('Marking archaic spellings…')
    conn.execute('UPDATE words SET archaic_spelling = 0, spelling_of = NULL')
    if not freq_db.exists():
        print(f'  (corpus_frequencies.db not found, skipped: {freq_db})')
        return

    fconn = sqlite3.connect(f'file:{freq_db}?mode=ro', uri=True)
    modern = {w: o for w, o in fconn.execute(
        "SELECT word, occurrence_count FROM corpus_word_frequency "
        " WHERE corpus_name = 'culturax_ro'")}
    fconn.close()

    marked = []
    for (word,) in conn.execute('SELECT word FROM words').fetchall():
        own = modern.get(word, 0)
        for pattern, repl in _SPELLING_RULES:
            twin = pattern.sub(repl, word)
            if twin == word:
                continue
            twin_n = modern.get(twin, 0)
            if twin_n and twin_n >= TWIN_RATIO * max(own, 1):
                marked.append((twin, word))
                break

    conn.executemany(
        'UPDATE words SET archaic_spelling = 1, spelling_of = ? WHERE word = ?', marked)
    print(f'  {len(marked):,} archaic spellings (twin ≥{TWIN_RATIO}× in the modern corpus)')


# ── DEX's own variant relation ───────────────────────────────────────────────────
#
# `mark_archaic_spellings()` above guesses at the same thing from the spelling, and the
# table of measured precisions there is the argument for this function: the rules that
# would catch `sofragerie → sufragerie` or `coprins → cuprins` are the ones that had to
# be rejected, because `o → u` fires 1,984 times to find 124 twins. The right answers
# were never the problem; telling them from the noise was.
#
# DEX already knows. `EntryLexeme` groups the lexemes of one dictionary entry and marks
# which of them is the headword: `main = 1` is the form the entry is filed under, `main
# = 0` are the variants of it that dexonline lists alongside. 53,618 rows say `main = 0`,
# and 4,773 of them are shortlist words. No spelling heuristic is involved, so the
# relation reaches pairs that share no visible rule at all — `octomvre/octombrie`,
# `hiclean/viclean`, `ghinărar/general`.
#
# Two restrictions, both of which cost recall on purpose:
#
# 1. **The word must never be a headword itself.** 1,998 shortlist words are `main = 0`
#    in one entry and `main = 1` in another, usually because they carry a sense of their
#    own that DEX files separately — `momiță` is a variant of `maimuță` in one entry and
#    the word for a sweetbread in another, `partită` of `partidă` and also the musical
#    form, `băcălie` of `băcănie` and also the grocer's wife. Admitting them adds 1,039
#    words at an inspected error rate around 5%, and the errors are invisible: a hidden
#    word is simply not there. So they stay visible. `archaic_spelling` picks up the
#    unambiguous half of that group anyway (`condițiune`, `advocat`) via the regex rules.
#
#    **One carve-out, and it is DEX contradicting itself rather than us second-guessing
#    it: a word whose entire definition is „vezi X".** The justification above is that a
#    self-heading form carries a sense of its own; an entry whose whole text is a pointer
#    is the dictionary saying it does not. 175 words are in that state, all 175 linked by
#    the relation, and 66 of them were kept visible by restriction 1 alone — `volintir`
#    („vezi voluntar"), `țignal` („vezi semnal"), `contimporan`, `nuor`. A reader who
#    opens one gets no definition, because there is none to get.
#
#    The pointer also **names the head**, which is better evidence than the edit-distance
#    pick below: measured over the 47 pointer words the relation already flagged, the two
#    agree on 46 and the one disagreement is DEX's („uiet" → *huiet*, not *vuiet*).
#
# 2. **The headword must clear TWIN_RATIO in the modern corpus**, exactly as the spelling
#    rules must. Without it this hides the pairs where *both* forms are forgotten, which
#    are the project's own material rather than noise: `antereu/anteriu`,
#    `amploiat/amploaiat`, `zalhana/zahana`, `lighioaie/lighioană`, `pătlăgea/pătlăgică`
#    — 53 in the default view.
#
#    **This one is not waived for the pointer definitions**, and it is what makes the
#    carve-out above safe. „vezi X" says the word has no sense of its own; it does not say
#    X is alive. Gated, the pointers split cleanly down the middle — 31 hidden, every one
#    pointing at an ordinary modern word (`voluntar` 1.38M, `semnal` 2.59M, `nor` 261k),
#    and 68 left standing, every one pointing at a word as dead as itself
#    (`bejănar`→*băjenar* 138, `bălsămit`→*bălsămat* 52, `jălbar`→*jelbar* 24). Waiving it
#    too would hide the second group, which is exactly the material the project is for —
#    and it would hide it *because* the dictionary was terse about it.
#
# It is a separate flag from `archaic_spelling` rather than folded into it, and the two
# are kept **disjoint**: a word the regex rules already claimed is not marked here. Each
# control then reveals its own whole set, instead of „grafii vechi: cu" uncovering 127
# words that another row is still hiding.
_VARIANT_ENTRY_SQL = """
    SELECT el.entryId, lx.formNoAccent, el.main
      FROM EntryLexeme el
      JOIN Lexeme lx ON lx.id = el.lexemeId
     WHERE lx.formNoAccent IS NOT NULL AND lx.formNoAccent != ''
"""

# Deliberately only „vezi X", and only when that is the *whole* definition: all 175
# pointer rows in the build are exactly that shape, none is `v. X`, and none names two
# targets or trails a gloss. A looser pattern would start reading the first line of an
# ordinary definition that happens to cross-reference something.
_POINTER_DEF = re.compile(r'^\s*vezi\s+([^\s,;.]+)\s*\.?\s*$', re.IGNORECASE)


def pointer_target(definition: str | None) -> str | None:
    """The word a „vezi X" definition points at, or None if it is a real definition."""
    m = _POINTER_DEF.match(definition or '')
    return normalize(m.group(1)) if m else None


def _edit_distance(a: str, b: str) -> int:
    """Levenshtein distance. Only ever called on two short words."""
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def load_dex_variants(lexemes_db: Path) -> tuple[dict[str, set[str]], set[str]]:
    """Read EntryLexeme → ({variant form: headwords it varies from}, {every headword}).

    Both halves are needed: the first says what a word is a variant *of*, the second is
    restriction 1 above — a form that heads an entry of its own is left alone.
    """
    heads_of: dict[str, set[str]] = {}
    all_heads: set[str] = set()
    if not lexemes_db.exists():
        return heads_of, all_heads

    lconn = sqlite3.connect(f'file:{lexemes_db}?mode=ro', uri=True)
    try:
        entries: dict[int, list[tuple[str, int]]] = {}
        for entry_id, form, main in lconn.execute(_VARIANT_ENTRY_SQL):
            entries.setdefault(entry_id, []).append((normalize(form), int(main)))
    except sqlite3.OperationalError:
        # An older lexemes.db built before extract_taxonomy.py loaded EntryLexeme.
        lconn.close()
        return heads_of, all_heads
    lconn.close()

    for members in entries.values():
        heads = {f for f, main in members if main == 1}
        all_heads |= heads
        for form, main in members:
            if main == 1:
                continue
            others = heads - {form}
            if others:
                heads_of.setdefault(form, set()).update(others)
    return heads_of, all_heads


def load_paradigm_modern(inflected_db: Path, modern: dict[str, int]) -> dict[str, int]:
    """lemma → modern occurrences summed over its whole inflectional paradigm.

    Used for the *headword* side of the ratio only. **A surface count is not usable
    there, and a verb is where it shows:** `lăcrima` has exactly zero occurrences in
    CulturaX as the bare infinitive — the paradigm carries them all — so gating on
    surface counts threw the real headword out and left `lăcrăma` labelled a variant of
    `reclama`, the only co-headword in its entry with a countable citation form.

    The sum is naive — a form claimed by several lemmas is credited to each in full,
    where `validate_diachronic.aggregate_by_family` would split it by headword
    prominence. That is tolerable *on this side*, because a head only has to clear a
    floor and over-crediting it can at most confirm what its own citation form already
    said. It is not tolerable on the variant's side, which is why the variant is measured
    by its surface count instead: see mark_dex_variants().
    """
    if not inflected_db.exists():
        return {}
    iconn = sqlite3.connect(f'file:{inflected_db}?mode=ro', uri=True)
    totals: dict[str, int] = {}
    for lemma, form in iconn.execute(
            'SELECT lx.lemma, i.form FROM inflected i JOIN lexeme lx '
            '  ON lx.lexeme_id = i.lexeme_id'):
        n = modern.get(form)
        if n:
            key = normalize(lemma)
            totals[key] = totals.get(key, 0) + n
    iconn.close()
    return totals


def mark_dex_variants(
    conn: sqlite3.Connection, lexemes_db: Path, freq_db: Path, inflected_db: Path
) -> None:
    """Populate words.dex_variant / words.dex_variant_of. Idempotent.

    Must run *after* mark_archaic_spellings(), which gets first claim on the overlap so
    the two flags stay disjoint.
    """
    print('Marking DEX variant forms…')
    conn.execute('UPDATE words SET dex_variant = 0, dex_variant_of = NULL')

    # Both empty, not just `heads_of`: an entry table that yields heads but no variants
    # is a legitimate (if odd) read, and the „vezi X" path does not need the relation at
    # all. Only a table that produced nothing whatsoever means the db predates
    # extract_taxonomy.py loading EntryLexeme, which is the case worth bailing on.
    heads_of, all_heads = load_dex_variants(lexemes_db)
    if not heads_of and not all_heads:
        print(f'  (no EntryLexeme rows found, skipped: {lexemes_db})')
        return
    if not freq_db.exists():
        print(f'  (corpus_frequencies.db not found, skipped: {freq_db})')
        return

    fconn = sqlite3.connect(f'file:{freq_db}?mode=ro', uri=True)
    modern = {w: o for w, o in fconn.execute(
        "SELECT word, occurrence_count FROM corpus_word_frequency "
        " WHERE corpus_name = 'culturax_ro'")}
    fconn.close()

    # Presence of the file, not truthiness of the map it yields: an empty map is a
    # legitimate outcome (no paradigm form appears in the corpus) and head_count() falls
    # back to surface counts for it, whereas a missing file means the build is
    # misconfigured and every head would be judged on its citation form alone.
    if not inflected_db.exists():
        print(f'  (inflected_forms.db not found, skipped: {inflected_db})')
        return
    family = load_paradigm_modern(inflected_db, modern)

    def head_count(w: str) -> int:
        # max, not the paradigm figure alone: a head absent from the paradigm map still
        # has its own surface count, and reading it as 0 would fail every gate.
        return max(family.get(w, 0), modern.get(w, 0))

    # **The two sides of the ratio are measured differently, and that asymmetry is the
    # question rather than a bias in it.** What is being judged about the variant is a
    # *spelling*, which is one surface form by definition — `tinereță` is written 381
    # times against `tinerețe`'s 227,064, and that is the whole finding. Summing its
    # paradigm instead credits it with its own headword's usage, because the two share
    # nearly every inflected form: `tinereță` comes out at 227,445 and reads as alive.
    # The head, by contrast, is a lemma, and a lemma's usage genuinely lives across its
    # paradigm — `lăcrima` is 0 as an infinitive and 16,393 as a verb.
    marked = []
    pointers = 0
    for word, archaic, definition in conn.execute(
            'SELECT word, COALESCE(archaic_spelling, 0), definition FROM words'
            ).fetchall():
        if archaic:
            continue
        # A definition that is only „vezi X" is DEX naming the head itself, and is the
        # one thing that overrides restriction 1 — see the carve-out above. It stands on
        # its own: the relation need not link the pair, because the prose already did.
        pointer = pointer_target(definition)
        if not pointer and word in all_heads:
            continue
        floor = TWIN_RATIO * max(modern.get(word, 0), 1)

        head = None
        if pointer and pointer != word and head_count(pointer) >= floor:
            head = pointer
        else:
            # Fallback, and also the whole of the ordinary path. A pointer whose target
            # is as dead as the word usually means the pair really is two dead forms and
            # nothing is hidden — but not always: „uiet · vezi huiet" names a twin nobody
            # writes either, while the entry's own head is the living `vuiet`. Reading
            # only the prose there would lose a variant the relation had right.
            heads = heads_of.get(word)
            if not heads:
                continue
            # Which head this is a variant *of* is settled first, and by spelling alone.
            # Letting the gate shortlist the candidates instead put `lăcrăma` under
            # `reclama` — its entry's other headword, and the only one whose citation
            # form the corpus could count. Nearest spelling, count as the tie-break.
            head = min(heads, key=lambda h: (_edit_distance(word, h), -head_count(h), h))
            if head_count(head) < floor:
                continue
        marked.append((head, word))
        pointers += bool(pointer)

    conn.executemany(
        'UPDATE words SET dex_variant = 1, dex_variant_of = ? WHERE word = ?', marked)
    print(f'  {len(marked):,} DEX variant forms '
          f'(headword ≥{TWIN_RATIO}× in the modern corpus over its whole paradigm, '
          f'and not a headword itself) — {pointers:,} of them named by a '
          f'„vezi X" definition')


# ── Deverbal nouns whose verb is already on the list ─────────────────────────────
#
# `zăhăială` is defined, in full, as "Faptul de a (se) zăhăi" — and `zăhăi` is three
# rows away in the same list. The noun is not a second find; it is the same find twice,
# and the second copy carries no information the first did not.
#
# **The flag is about the duplication, not about the derivation**, which is why the base
# verb has to be *on the list and visible* for the noun to be hidden. Marking every
# deverbal noun instead reads as a rule about word formation and quietly deletes 563
# words whose verb is nowhere in the shortlist — `pospăială` without `pospăi` is the only
# place a reader would ever meet that root.
#
# The visibility half is the part that is easy to get wrong. Measured on the 2026-08-12
# build, the naive "verb is in the table" rule fires on 166 words, and for **10 of the 25
# it removes from the default view the verb is not in the default view either** —
# `împământeni` is `regional_only`, `pospăi` is in the curiosity seam. There the noun is
# the only member of the pair anyone can see, so hiding it is not deduplication, it is
# deletion. Requiring the verb to be at least as visible as the noun costs 17 words and
# removes that whole class of error.
#
# No morphological check on top of the definition. Seven of the pairs share fewer than
# four leading characters (`usebire`/`osebi`, `oțerire`/`oțărî`, `raznă`/`răzleți`), and
# all seven are genuine — DEX asserting the derivation is better evidence than string
# similarity is, so a prefix requirement would only cost real hits.
_DEVERBAL_DEF_RE = re.compile(
    r'^\s*(?:Faptul|Ac[țt]iunea)\s+de\s+a\s+(?:\(\s*se\s*\)\s+|se\s+)?'
    r'([^\W\d_]+)', re.IGNORECASE | re.UNICODE)

# The class flags a base verb must be free of before its noun may be hidden behind it.
_HIDE_FLAGS = ('regional_only', 'variant_like', 'archaic_spelling', 'dex_variant',
               'diminutive_like')


def mark_deverbal_nouns(conn: sqlite3.Connection) -> None:
    """Populate words.deverbal_like / words.deverbal_of. Idempotent.

    **Must run after every other mark_* step**: it reads their flags to decide whether
    the base verb is visible, so running it earlier silently marks nouns whose verb turns
    out to be hidden a moment later.
    """
    print('Marking deverbal nouns…')
    conn.execute('UPDATE words SET deverbal_like = 0, deverbal_of = NULL')

    # Only the flag columns this database actually has — a migration may be applying
    # these one at a time, and a missing column should degrade the visibility check
    # rather than abort the step.
    have = {r[1] for r in conn.execute('PRAGMA table_info(words)')}
    flags = [c for c in _HIDE_FLAGS if c in have]
    cols = ''.join(f', {c}' for c in flags)
    rows = {r[0]: r for r in conn.execute(
        f'SELECT word, definition, seam{cols} FROM words').fetchall()}

    def unflagged(r) -> bool:
        return not any(r[i] for i in range(3, 3 + len(flags)))

    marked = []
    for word, row in rows.items():
        definition = row[1]
        if not definition:
            continue
        m = _DEVERBAL_DEF_RE.match(definition.split('|')[0].strip())
        if not m:
            continue
        verb = normalize(m.group(1))
        base = rows.get(verb)
        if base is None or verb == word:
            continue
        # At least as visible as the noun: no hide-flag of its own, and in the same seam
        # or the more visible one. Otherwise this hides the pair rather than the copy.
        if unflagged(base) and (base[2] == row[2] or base[2] == 'relevant'):
            marked.append((verb, word))

    conn.executemany(
        'UPDATE words SET deverbal_like = 1, deverbal_of = ? WHERE word = ?', marked)
    print(f'  {len(marked):,} deverbal nouns whose verb is on the list and visible')


def mark_modern_band(conn: sqlite3.Connection, freq_db: Path) -> None:
    """Bucket `modern_occ` into 0–3, using the pipeline's own rescaled thresholds.

    Counterintuitively, **more modern usage is better material here**. The words with a
    few thousand modern occurrences are the ones people recognise as forgotten — `birjă`,
    `zapciu`, `vechil`, `cocoană`, `dorobanț` — while the words at zero are dictionary
    ghosts that were never really in circulation (`celșag`, `racaleț`, `barabor`). The
    shortlist score already knows this; this column lets a reader sort on it directly.

    The edges come from validate_diachronic's MODERN_RARE_OCC / MODERN_ALIVE_OCC, run
    through scaled_modern_thresholds() against the current panel size. That indirection
    is the point: an absolute count means nothing except relative to how much modern text
    was read, so hardcoding 500/2000 in PHP would silently change meaning the moment a
    corpus is added. Storing a band instead keeps every threshold on this side of the
    build, where it can be rescaled.
    """
    modern_tokens = 0
    if freq_db.exists():
        fconn = sqlite3.connect(f'file:{freq_db}?mode=ro', uri=True)
        try:
            modern_tokens = sum(_corpus_tokens(fconn, c) for c in _MODERN_CORPORA)
        finally:
            fconn.close()

    rare_occ, _alive_occ = _scaled_modern_thresholds(modern_tokens)
    # Three bands, not four. `alive_occ` is also make_shortlist's own eligibility ceiling
    # — a word at or above it is "simply in use" and never enters the shortlist — so a
    # fourth band is unreachable here by construction (measured: max modern_occ is 1,998
    # against an alive floor of 2,000). Offering it would be a control with nothing
    # behind it. Revisit if that gate ever moves.
    conn.execute(
        """UPDATE words SET modern_band = CASE
               WHEN modern_occ IS NULL THEN NULL
               WHEN modern_occ <= 0    THEN 0
               WHEN modern_occ < ?     THEN 1
               ELSE 2
           END""",
        (rare_occ,),
    )
    counts = dict(conn.execute(
        'SELECT modern_band, COUNT(*) FROM words WHERE modern_band IS NOT NULL '
        'GROUP BY modern_band').fetchall())
    labels = {0: 'absent', 1: f'1–{rare_occ - 1}', 2: f'{rare_occ}+'}
    print('  ' + ' · '.join(f'{labels[b]}: {counts.get(b, 0):,}' for b in (0, 1, 2)))


class BuildError(RuntimeError):
    """The build stopped before publishing. The previous output is untouched."""


@dataclasses.dataclass(frozen=True)
class Inputs:
    """Every file the build reads besides the shortlist, with its policy.

    `required` inputs must exist for a production build: without one, a scored flag or
    a hide-control silently changes what visitors see. `optional` inputs add a section
    the app renders only when present. `allow_missing_inputs=True` (CLI
    `--allow-missing-inputs`) turns a missing required input into a warning; tests and
    partial checkouts use it.
    """
    web: Path = WEB_PATH
    defs: Path = DEFINITIONS_PATH
    dict_sources: Path = DICT_SOURCES_PATH
    synonyms: Path = SYNONYMS_PATH
    meanings: Path = MEANINGS_PATH
    lexemes: Path = LEXEMES_PATH
    freq: Path = FREQ_PATH
    inflected: Path = INFLECTED_PATH
    editorial: Path = EDITORIAL_PATH

    REQUIRED = ('defs', 'dict_sources', 'lexemes', 'freq', 'inflected')
    OPTIONAL = ('web', 'synonyms', 'meanings', 'editorial')

    def missing(self) -> tuple[list[str], list[str]]:
        """Return (missing required names, missing optional names)."""
        def gone(names):
            return [f'{n}: {getattr(self, n)}' for n in names
                    if not Path(getattr(self, n)).exists()]
        return gone(self.REQUIRED), gone(self.OPTIONAL)


# Columns, tables and indexes a candidate must have. The PHP app queries all of them.
REQUIRED_TABLES = ('words', 'vocab', 'senses', 'sense_citations')
REQUIRED_WORD_COLUMNS = (
    'word', 'word_normalized', 'dex_frequency', 'verdict', 'confidence_tier', 'log_ratio',
    'hist_ppm', 'modern_ppm', 'subtitle_ppm', 'dex_pos', 'dex_register', 'dex_domain',
    'dex_etymology', 'is_forgotten', 'has_definition', 'total_results', 'in_wild',
    'web_score', 'top_url', 'last_seen_approx', 'provider', 'definition', 'word_tier',
    'dict_count', 'zipf_frequency', 'en_zipf', 'proper_noun_like', 'sources', 'word_id',
    'hist_occ', 'hist_docs', 'modern_occ', 'modern_docs', 'modern_occ_loose',
    'family_ratio', 'rank_shift', 'newest_dict_year', 'in_current_dict', 'quality_score',
    'seam', 'regional_only', 'variant_like', 'variant_of', 'diminutive_like',
    'archaic_spelling', 'spelling_of', 'dex_variant', 'dex_variant_of', 'deverbal_like',
    'deverbal_of', 'synonyms', 'antonyms', 'editor_pick', 'editor_demote', 'modern_band',
    'dex_etymon',
)
REQUIRED_INDEXES = (
    'idx_words_word_id', 'idx_vocab_kind', 'idx_words_verdict', 'idx_words_tier',
    'idx_words_word_tier', 'idx_words_word', 'idx_words_modern', 'idx_words_normalized',
    'idx_words_zipf', 'idx_words_default', 'idx_words_modern_occ', 'idx_words_editor',
)
_SIDECAR_SUFFIXES = ('-wal', '-shm', '-journal')


def _sidecars(path: Path) -> list[Path]:
    return [path.with_name(path.name + sfx) for sfx in _SIDECAR_SUFFIXES]


def _remove_quietly(path: Path) -> None:
    with contextlib.suppress(FileNotFoundError):
        path.unlink()


def _fsync_dir(directory: Path) -> None:
    fd = os.open(str(directory), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


@contextlib.contextmanager
def _output_lock(out: Path):
    """Exclusive non-blocking flock on `<out>.lock`; raises BuildError when held.

    Same pattern as scrape_synonyms.acquire_host_lock: the kernel drops the lock when
    the process dies, and the pid inside is only read back to name the holder.
    """
    lock_path = out.with_name(out.name + '.lock')
    handle = lock_path.open('a+', encoding='utf-8')
    try:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.seek(0)
            holder = handle.read().strip() or 'holder unknown'
            raise BuildError(f'another build holds {lock_path} ({holder})') from None
        handle.seek(0)
        handle.truncate()
        handle.write(f'pid {os.getpid()}\n')
        handle.flush()
        yield
    finally:
        handle.close()


def finalize_candidate(path: Path) -> None:
    """Make the candidate one self-contained file.

    Checkpoints the WAL into the main file, then switches the journal mode to DELETE.
    The mode lives in the file header, so the published database needs no `-wal` or
    `-shm` sidecar and a reader never replays a log that belongs to another file.
    """
    conn = sqlite3.connect(str(path))
    try:
        conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        mode = conn.execute('PRAGMA journal_mode=DELETE').fetchone()[0]
        if mode.lower() != 'delete':
            raise BuildError(f'could not switch the candidate to DELETE mode (got {mode})')
        conn.execute('VACUUM')
    finally:
        conn.close()
    leftovers = [p for p in _sidecars(path) if p.exists()]
    if leftovers:
        raise BuildError(f'candidate still has sidecars: {[p.name for p in leftovers]}')


def validate_candidate(path: Path, registry_path: Path, *, min_words: int,
                       previous: Path | None = None, allow_shrink: bool = False) -> int:
    """Check a finished candidate. Return its word count; raise BuildError on any defect."""
    with open(path, 'rb') as f:
        header = f.read(100)
    if header[:16] != b'SQLite format 3\x00':
        raise BuildError('candidate is not an SQLite database')
    if header[18] != 1 or header[19] != 1:
        raise BuildError('candidate is not in DELETE journal mode (header says WAL)')

    conn = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
    try:
        problems = [r[0] for r in conn.execute('PRAGMA integrity_check')]
        if problems != ['ok']:
            raise BuildError(f'integrity_check failed: {problems[:3]}')

        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        missing = [t for t in REQUIRED_TABLES if t not in tables]
        if missing:
            raise BuildError(f'missing tables: {missing}')
        cols = {r[1] for r in conn.execute('PRAGMA table_info(words)')}
        missing = [c for c in REQUIRED_WORD_COLUMNS if c not in cols]
        if missing:
            raise BuildError(f'words is missing columns: {missing}')
        indexes = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
        missing = [i for i in REQUIRED_INDEXES if i not in indexes]
        if missing:
            raise BuildError(f'missing indexes: {missing}')

        total, with_id, distinct_ids = conn.execute(
            'SELECT COUNT(*), COUNT(word_id), COUNT(DISTINCT word_id) FROM words').fetchone()
        if total == 0:
            raise BuildError('candidate has no words')
        if total < min_words:
            raise BuildError(f'candidate has {total:,} words, below the minimum {min_words:,} '
                             f'(use --min-words for an intentionally small build)')
        if with_id != total:
            raise BuildError(f'{total - with_id} words have no word_id')
        if distinct_ids != total:
            raise BuildError('word_id values are not unique')

        registry = _word_ids.load_registry(registry_path)
        wrong = [w for w, i in conn.execute('SELECT word, word_id FROM words')
                 if registry.get(w) != i]
        if wrong:
            raise BuildError(f'{len(wrong)} word ids differ from the registry, e.g. {wrong[:3]}')
    finally:
        conn.close()

    if previous is not None and previous.exists() and not allow_shrink:
        try:
            pconn = sqlite3.connect(f'file:{previous}?mode=ro', uri=True)
            try:
                old_total = pconn.execute('SELECT COUNT(*) FROM words').fetchone()[0]
            finally:
                pconn.close()
        except sqlite3.Error:
            old_total = 0        # an unreadable previous output is no baseline
        if old_total and total < old_total * SHRINK_FLOOR:
            raise BuildError(f'candidate has {total:,} words, under {SHRINK_FLOOR:.0%} of the '
                             f'previous output ({old_total:,}); use --allow-shrink if intended')
    return total


def build(shortlist: Path, rare: Path | None, web: Path | None, defs: Path | None,
          out: Path, *,
          inputs: Inputs | None = None,
          registry_path: Path = _word_ids.REGISTRY_PATH,
          min_words: int = MIN_WORDS_DEFAULT,
          allow_missing_inputs: bool = False,
          allow_shrink: bool = False,
          discard_stale_wal: bool = False) -> None:
    """Build `out` atomically.

    Steps: take the registry and output locks; build a candidate in a unique temp file
    in `out`'s directory; checkpoint it into a self-contained DELETE-mode file;
    validate it; then `os.replace` it over `out`. Any failure removes the temp file and
    leaves the previous `out` byte-identical. `rare` is unused (kept for the old
    signature); `web` and `defs` override `inputs` for the same reason.

    **ID registry.** `data/word_ids.tsv` is append-only and is NOT part of the atomic
    swap. Ids are appended while the candidate is being built. If the build fails
    later, the appended ids stay in the registry and no database uses them yet. That is
    harmless: the next build reuses them. A registry id is never removed or changed.
    There is no two-file transaction.

    **Stale sidecars.** A `-wal` or `-shm` file beside the old output belongs to the
    old file. A new DELETE-mode database next to an old `-wal` can be corrupted by
    replay. Empty sidecars are removed just before the replace. A non-empty `-wal`
    holds committed data of the old file, so the build refuses unless
    `discard_stale_wal=True`.
    """
    shortlist, out, registry_path = Path(shortlist), Path(out), Path(registry_path)
    inputs = inputs or Inputs()
    if web is not None:
        inputs = dataclasses.replace(inputs, web=Path(web))
    if defs is not None:
        inputs = dataclasses.replace(inputs, defs=Path(defs))
    if not shortlist.exists():
        raise BuildError(f'Missing: {shortlist}')
    missing_required, missing_optional = inputs.missing()
    if missing_required and not allow_missing_inputs:
        raise BuildError('required inputs are missing (use --allow-missing-inputs for a '
                         'partial build):\n  ' + '\n  '.join(missing_required))
    for m in missing_required:
        print(f'  WARNING: required input missing, feature skipped: {m}')
    for m in missing_optional:
        print(f'  note: optional input missing, skipped: {m}')

    out.parent.mkdir(parents=True, exist_ok=True)
    tmp: Path | None = None
    with _word_ids.registry_lock(registry_path):
        with _output_lock(out):
            # Under the lock no other builder runs, so any build temp left here is an
            # orphan from a killed run.
            for orphan in out.parent.glob(out.name + '.build-*'):
                _remove_quietly(orphan)
            fd, tmp_name = tempfile.mkstemp(prefix=out.name + '.build-', suffix='.tmp',
                                            dir=str(out.parent))
            os.close(fd)
            tmp = Path(tmp_name)
            try:
                conn = sqlite3.connect(str(tmp))
                try:
                    _populate(conn, shortlist, inputs, registry_path)
                    conn.commit()
                finally:
                    conn.close()
                finalize_candidate(tmp)
                total = validate_candidate(tmp, registry_path, min_words=min_words,
                                           previous=out, allow_shrink=allow_shrink)
                with open(tmp, 'rb') as f:
                    os.fsync(f.fileno())
                _clear_stale_sidecars(out, discard_stale_wal)
                os.replace(tmp, out)
                tmp = None
                _fsync_dir(out.parent)
            finally:
                if tmp is not None:
                    _remove_quietly(tmp)
                    for sc in _sidecars(tmp):
                        _remove_quietly(sc)

    size_mb = out.stat().st_size / 1024 / 1024
    print(f'Done → {out}  ({total:,} words, {size_mb:.1f} MB)')


def _clear_stale_sidecars(out: Path, discard_stale_wal: bool) -> None:
    """Remove `-wal`/`-shm`/`-journal` files of the OLD output just before the replace."""
    wal = out.with_name(out.name + '-wal')
    if wal.exists() and wal.stat().st_size > 0 and not discard_stale_wal:
        raise BuildError(f'{wal} is not empty: the previous output has uncheckpointed data. '
                         'Open it once with sqlite3 to checkpoint, or use --discard-stale-wal.')
    for sc in _sidecars(out):
        _remove_quietly(sc)


def _populate(conn: sqlite3.Connection, shortlist: Path, inputs: Inputs,
              registry_path: Path) -> None:
    """Create every table and fill the candidate. Nothing here touches the output."""
    web, defs = inputs.web, inputs.defs
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute("""
        CREATE TABLE words (
            word             TEXT PRIMARY KEY,
            word_normalized  TEXT,
            dex_frequency    REAL,
            verdict          TEXT,
            confidence_tier  TEXT,
            log_ratio        REAL,
            hist_ppm         REAL,
            modern_ppm       REAL,
            subtitle_ppm     REAL,
            dex_pos          TEXT,
            dex_register     TEXT,
            dex_domain       TEXT,
            dex_etymology    TEXT,
            is_forgotten     INTEGER,
            has_definition   INTEGER,
            total_results    INTEGER,
            in_wild          INTEGER,
            web_score        TEXT,
            top_url          TEXT,
            last_seen_approx TEXT,
            provider         TEXT,
            definition       TEXT,
            word_tier        TEXT DEFAULT 'forgotten',
            dict_count       INTEGER,
            zipf_frequency   REAL,
            en_zipf          REAL,
            proper_noun_like INTEGER,
            sources          TEXT,
            word_id          INTEGER,
            -- Added in the 2026-08-07 rescore. Paradigm-level counts replace the ppm
            -- columns above for every filtering decision; the ppm ones stay so the two
            -- can be compared.
            hist_occ         INTEGER,
            hist_docs        INTEGER,
            modern_occ       INTEGER,
            modern_docs      INTEGER,
            modern_occ_loose INTEGER,
            family_ratio     REAL,
            rank_shift       REAL,
            newest_dict_year INTEGER,
            in_current_dict  INTEGER,
            quality_score    INTEGER,
            seam             TEXT DEFAULT 'relevant',
            regional_only    INTEGER,
            variant_like     INTEGER,
            variant_of       TEXT,
            -- Set by mark_diminutives() below, after definitions are merged: the
            -- strongest signal is the DEX definition itself saying "Diminutiv al lui X".
            diminutive_like  INTEGER,
            -- Set by mark_archaic_spellings(): the word is an obsolete spelling of a word
            -- that is alive under a modern one (`situațiune` → `situație`). `spelling_of`
            -- holds the modern twin so the UI can name it rather than just hiding a row.
            archaic_spelling INTEGER,
            spelling_of      TEXT,
            -- Set by mark_dex_variants(): DEX itself files this form as a variant of a
            -- headword that is still thoroughly alive (`sofragerie` → `sufragerie`),
            -- read off EntryLexeme.main rather than guessed from the spelling.
            -- Deliberately disjoint from archaic_spelling — the regex rules get first
            -- claim on the overlap, so each control reveals its own whole set.
            dex_variant      INTEGER,
            dex_variant_of   TEXT,
            -- Set by mark_deverbal_nouns(), which runs last because it reads every flag
            -- above: the word is a noun defined as "Faptul de a X" whose verb X is on
            -- the list *and visible*. `deverbal_of` holds the verb.
            deverbal_like    INTEGER,
            deverbal_of      TEXT,
            -- Scraped from dexonline.ro by scrape_synonyms.py. Not in the dump: the
            -- Litera dictionaries (Sinonime, Sinonime82, Antonime) are redacted to 23
            -- characters there, so `dict_count` knows a word is in them but not what
            -- they say.
            synonyms         TEXT,
            antonyms         TEXT,
            -- Curator marks, from data/editorial.tsv via tools/export_editorial.py.
            -- Deliberately NOT part of quality_score: the score says how good the
            -- evidence is, these say what a human thought, and mixing them makes the
            -- judgement unappealable — the same reason the four class flags stay out
            -- of it. `editor_demote` is the only signal in the project allowed to
            -- subtract from the default view, and only through a visible control.
            -- Community marks never reach this table: they are aggregated live and may
            -- only reorder. See vote_counts_subquery() in public/api/_appdb.php.
            editor_pick      INTEGER,
            editor_demote    INTEGER,
            -- How much life the word still has in modern Romanian, bucketed by
            -- mark_modern_band() below. 0 absent · 1 faint · 2 rare · 3 in circulation.
            -- An integer rather than a raw count because the UI must not carry a
            -- threshold: occurrence counts only mean something relative to how much
            -- modern text was read, so the edges are rescaled at build time from the
            -- pipeline's own MODERN_RARE_OCC / MODERN_ALIVE_OCC.
            modern_band      INTEGER,
            -- Set by merge_senses(), from extract_meanings.py's meanings.db. The
            -- `Meaning.type=1` rows (the etymon itself, e.g. `badana` for `bidinea`) —
            -- `dex_etymology` above already holds the *language* name from taxonomy
            -- tags; this gives the etymology chip something to say beyond it.
            dex_etymon       TEXT
        )
    """)
    # Full sense trees (docs/senses-plan.md). Two tables rather than a `\n`-joined
    # column on `words`: citations are the bulk of the payload and the panel collapses
    # them, so the query that renders the numbered senses should not have to carry them.
    conn.execute("""
        CREATE TABLE senses (
            word        TEXT    NOT NULL,
            ord         INTEGER NOT NULL,   -- 0-based display order
            breadcrumb  TEXT    NOT NULL,   -- '1.', '1.1.', '' for compound/expression
            depth       INTEGER NOT NULL,   -- 1 for '1.', 2 for '1.1.'; 1 for kind != 'sense'
            kind        TEXT    NOT NULL,   -- 'sense' | 'compound' | 'expression'
            text        TEXT    NOT NULL,
            tags        TEXT,               -- pipe-delimited meaning-level taxonomy tags
            -- Pipe-delimited `Relation.type=1` targets (extract_meanings.py's
            -- meaning_synonyms). Set whenever DEX has one, even when `text` is
            -- non-empty (a sense can have both, and dexonline shows both — see
            -- zăticni sense '2.'). When `text` is empty, this is the sense's ONLY
            -- content and the reason it wasn't dropped by merge_senses(); see
            -- _process_sense_tree()'s docstring.
            synonyms    TEXT,
            PRIMARY KEY (word, ord)
        )
    """)
    conn.execute("""
        CREATE TABLE sense_citations (
            word       TEXT    NOT NULL,
            sense_ord  INTEGER NOT NULL,
            ord        INTEGER NOT NULL,
            text       TEXT    NOT NULL,
            PRIMARY KEY (word, sense_ord, ord)
        )
    """)

    print(f'Loading shortlist from {shortlist}…')
    with open(shortlist, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            conn.execute(
                """INSERT OR IGNORE INTO words
                   (word, dex_frequency, verdict, confidence_tier, log_ratio,
                    hist_ppm, modern_ppm, subtitle_ppm,
                    dex_pos, dex_register, dex_domain,
                    dex_etymology, is_forgotten, has_definition, word_tier,
                    dict_count,
                    hist_occ, hist_docs, modern_occ, modern_docs, modern_occ_loose,
                    family_ratio, rank_shift, newest_dict_year, in_current_dict,
                    quality_score, seam, regional_only, variant_like, variant_of)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                           ?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    row['word'],
                    _float(row.get('dex_frequency', '')),
                    row.get('verdict') or None,
                    row.get('confidence_tier') or None,
                    _float(row.get('log_ratio', '')),
                    _float(row.get('hist_ppm', '')),
                    _float(row.get('modern_ppm', '')),
                    _float(row.get('subtitle_ppm', '')),
                    _normalize_sep(row.get('dex_pos')),
                    _normalize_sep(row.get('dex_register')),
                    _normalize_sep(row.get('dex_domain')),
                    _normalize_sep(row.get('dex_etymology')),
                    _bool(row.get('is_forgotten', '')),
                    _bool(row.get('has_definition', '')),
                    'forgotten',
                    _int(row.get('dict_count', '')),
                    _int(row.get('hist_occ', '')),
                    _int(row.get('hist_docs', '')),
                    _int(row.get('modern_occ', '')),
                    _int(row.get('modern_docs', '')),
                    _int(row.get('modern_occ_loose', '')),
                    _float(row.get('family_ratio', '')),
                    _float(row.get('rank_shift', '')),
                    _int(row.get('newest_dict_year', '')),
                    _int(row.get('in_current_dict', '')),
                    _int(row.get('quality_score', '')),
                    row.get('seam') or 'relevant',
                    _int(row.get('regional_only', '')),
                    _int(row.get('variant_like', '')),
                    row.get('variant_of') or None,
                ),
            )

    # The `rare_in_use` tier used to be loaded here from rare_words_wordfreq.csv. It is
    # gone, and the reason is worth keeping: it was decided by wordfreq's Romanian
    # frequency list, and that list has no resolution at the low end. Measured over 60,000
    # candidates, 99.6% score exactly 0.00 — the library has never heard of them — so its
    # lowest *real* scores are ordinary words like `haz` and `bețiv`, while `zapciu`,
    # `vornic` and `logofăt` are all 0.00 and indistinguishable. A tier defined on that
    # band could only ever hold common words, at any threshold.
    #
    # It also had zero overlap with the shortlist: all 219 rows were words this pipeline
    # had already measured against 17B tokens of CulturaX and correctly called still-used.
    # The idea it reached for — "old-flavoured but you would still meet it" — is now a
    # filter on the one list instead, via `modern_band` below, measured on the corpus.
    # See docs/BACKLOG.md, "the rare tab was measuring with a ruler that stops too high".

    if web.exists():
        print(f'Merging web validation from {web}…')
        with open(web, newline='', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                conn.execute(
                    """UPDATE words SET
                       total_results=?, in_wild=?, web_score=?,
                       top_url=?, last_seen_approx=?, provider=?
                       WHERE word=?""",
                    (
                        _int(row.get('total_results', '')),
                        _bool(row.get('in_wild', '')),
                        row.get('web_score') or None,
                        row.get('top_url') or None,
                        row.get('last_seen_approx') or None,
                        row.get('provider') or None,
                        row['word'],
                    ),
                )
    else:
        print(f'  (web validation file not found, skipping: {web})')

    if defs.exists():
        print(f'Merging definitions from {defs}…')
        dconn = sqlite3.connect(str(defs))
        for word, definition in dconn.execute('SELECT word, definition FROM definitions'):
            conn.execute('UPDATE words SET definition=? WHERE word=?', (definition, word))
        dconn.close()
        # Reconcile has_definition to reflect actual definition presence.
        conn.execute('UPDATE words SET has_definition = (definition IS NOT NULL)')
    else:
        print(f'  (definitions DB not found, skipping: {defs})')

    merge_dict_sources(conn, inputs.dict_sources)
    merge_synonyms(conn, inputs.synonyms)
    # Before every mark_* step below: they read words.definition, which this pass never
    # touches, so strictly it does not matter — but merges land before marks throughout
    # this file, and mark_deverbal_nouns() still has to run last regardless.
    merge_senses(conn, inputs.meanings)

    # After the definitions merge, not before — half the signal is the definition text.
    mark_diminutives(conn, inputs.lexemes)
    mark_archaic_spellings(conn, inputs.freq)
    # After mark_archaic_spellings, never before: the two flags are disjoint and the
    # regex rules get first claim on the 127 words both would take.
    mark_dex_variants(conn, inputs.lexemes, inputs.freq, inputs.inflected)
    # Last of the mark_* steps, and it has to stay last: it reads the flags the three
    # above set, to check the base verb is visible before hiding the noun behind it.
    mark_deverbal_nouns(conn)
    print('Bucketing modern usage…')
    mark_modern_band(conn, inputs.freq)

    # Must run before the vocab table is built, or the POS dropdown lists the old
    # taxonomy-derived values that almost nothing matches.
    lexemes_for_pos = inputs.lexemes
    if lexemes_for_pos.exists():
        print('Deriving dex_pos from Lexeme.modelType…')
        pos_map = load_pos_from_lexemes(lexemes_for_pos)
        updated = 0
        for (w,) in conn.execute('SELECT word FROM words').fetchall():
            pos = pos_map.get(w.lower())
            if pos:
                conn.execute('UPDATE words SET dex_pos = ? WHERE word = ?',
                             ('|'.join(sorted(pos)), w))
                updated += 1
        covered, total = conn.execute(
            "SELECT SUM(dex_pos IS NOT NULL AND dex_pos != ''), COUNT(*) FROM words"
        ).fetchone()
        print(f'  {updated:,} words given a model-derived POS '
              f'({covered:,}/{total:,} now carry one)')

    print('Building vocab table…')
    build_vocab_table(conn)

    conn.create_function('strip_diacritics', 1, _strip_diacritics)
    conn.execute('UPDATE words SET word_normalized = strip_diacritics(word)')

    # Populate zipf_frequency + en_zipf using wordfreq (optional)
    if _zipf is not None:
        print('Computing zipf frequencies…')
        rows = conn.execute('SELECT word FROM words').fetchall()
        batch = [(_zipf(r[0], 'ro'), _zipf(r[0], 'en'), r[0]) for r in rows]
        conn.executemany('UPDATE words SET zipf_frequency=?, en_zipf=? WHERE word=?', batch)
        print(f'  {len(batch)} rows updated')
    else:
        print('wordfreq not available — zipf_frequency/en_zipf left NULL')

    # Populate proper_noun_like from lexemes.db (optional).
    #
    # Flag a word only when DEX knows it *exclusively* as a capitalised headword. The
    # earlier version flagged anything that merely collided with one, which hid ordinary
    # nouns that happen to share a spelling with a surname or a place: `gheb` ("cocoașă")
    # was hidden because DEX also lists the name `Gheb`. Since these words are hidden by
    # default now, a false positive costs a real word rather than just a filter option.
    lexemes_path = inputs.lexemes
    if lexemes_path.exists():
        print('Computing proper_noun_like…')
        lconn = sqlite3.connect(str(lexemes_path))
        caps, lower = set(), set()
        for form, model_type in lconn.execute(
                'SELECT formNoAccent, modelType FROM Lexeme '
                " WHERE formNoAccent IS NOT NULL AND formNoAccent != ''"):
            # str.isupper() on the first character, not GLOB '[A-Z]*' — the latter is
            # ASCII-only and misses Ș/Ă/Î (Șerban, Ăst-, Împărat). modelType 'SP' is
            # DEX's own proper-noun model (America, Carpați, Alexandria).
            is_proper = form[0].isupper() or (model_type or '').strip() == 'SP'
            (caps if is_proper else lower).add(form.lower())
        lconn.close()
        proper_only = caps - lower
        conn.execute('UPDATE words SET proper_noun_like = 0')
        if proper_only:
            ph = ','.join('?' * len(proper_only))
            conn.execute(
                f'UPDATE words SET proper_noun_like = 1 WHERE word IN ({ph})',
                list(proper_only))
        marked = conn.execute(
            'SELECT COUNT(*) FROM words WHERE proper_noun_like = 1').fetchone()[0]
        print(f'  {len(proper_only):,} proper-only headwords in DEX → {marked} words marked '
              f'({len(caps & lower):,} capitalised forms ignored as ordinary words too)')
    else:
        print('lexemes.db not found — proper_noun_like left NULL')

    # Curator picks and demotes. Like the word ids below, this runs after every insert
    # path has landed so a mark cannot miss the row it belongs to.
    print('Applying curator marks…')
    picks, demotes, missing = _apply_editorial(conn, inputs.editorial)
    print(f'  {picks} pick, {demotes} demote'
          + (f' ({missing} in the file are not in this shortlist)' if missing else ''))

    # Permanent word ids for the compact ?w= share URLs. Runs last, so every
    # insert path (shortlist + rare-in-use) has landed and no word is missed.
    print('Assigning permanent word ids…')
    print(f'  {_apply_word_ids(conn, registry_path, hold_lock=False)} rows carry a word_id')

    # Indexes
    conn.execute('CREATE UNIQUE INDEX idx_words_word_id ON words(word_id)')
    conn.execute('CREATE INDEX idx_vocab_kind      ON vocab(kind)')
    conn.execute('CREATE INDEX idx_words_verdict   ON words(verdict)')
    conn.execute('CREATE INDEX idx_words_tier      ON words(confidence_tier)')
    conn.execute('CREATE INDEX idx_words_word_tier ON words(word_tier)')
    conn.execute('CREATE INDEX idx_words_word      ON words(word COLLATE NOCASE)')
    conn.execute('CREATE INDEX idx_words_modern    ON words(modern_ppm)')
    conn.execute('CREATE INDEX idx_words_normalized ON words(word_normalized)')
    conn.execute('CREATE INDEX idx_words_zipf       ON words(zipf_frequency)')
    # The default listing is (word_tier, seam) filtered and quality_score ordered, so it
    # gets a covering composite rather than three separate indexes.
    conn.execute('CREATE INDEX idx_words_default    '
                 'ON words(word_tier, seam, quality_score DESC)')
    conn.execute('CREATE INDEX idx_words_modern_occ ON words(modern_occ)')
    # The ★ list is `WHERE editor_pick = 1` over the whole table, and the default view
    # adds `editor_demote = 0` to every query.
    conn.execute('CREATE INDEX idx_words_editor      ON words(editor_pick, editor_demote)')



def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description='Build ui.db atomically (see docs/ui-db-build.md).')
    ap.add_argument('--out', type=Path, default=OUT_PATH)
    ap.add_argument('--registry', type=Path, default=_word_ids.REGISTRY_PATH,
                    help='permanent word-id registry (append-only)')
    ap.add_argument('--min-words', type=int, default=MIN_WORDS_DEFAULT,
                    help='refuse to publish a build with fewer words')
    ap.add_argument('--allow-missing-inputs', action='store_true',
                    help='warn instead of stopping when a required input is missing')
    ap.add_argument('--allow-shrink', action='store_true',
                    help='allow a build under half the size of the current output')
    ap.add_argument('--discard-stale-wal', action='store_true',
                    help='replace an output that has a non-empty -wal file')
    a = ap.parse_args(argv)
    try:
        build(SHORTLIST_PATH, RARE_PATH, WEB_PATH, DEFINITIONS_PATH, a.out,
              registry_path=a.registry, min_words=a.min_words,
              allow_missing_inputs=a.allow_missing_inputs, allow_shrink=a.allow_shrink,
              discard_stale_wal=a.discard_stale_wal)
    except (BuildError, _word_ids.RegistryLocked) as e:
        sys.exit(f'build_ui_db: {e}')


if __name__ == '__main__':
    main()
