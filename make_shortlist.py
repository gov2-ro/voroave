#!/usr/bin/env python3
"""
Score and split the diachronic results into the two lists the site actually shows.

Reads forgotten_words_diachronic.csv (output of validate_diachronic.py) and produces two
disjoint seams, because the project is chasing two different things:

  relevant   — seldom used but still relevant. In a dictionary published from 2005 on,
               attested historically, not regional, not an archaic respelling of a word
               people still use. This is the default view and what markers should spend
               their time on.
  curiosity  — the odd end: words that survive only in older or specialist dictionaries,
               regionalisms, and paradigm-sharing variants of current words. Interesting
               to browse, but they are not "forgotten Romanian" in the useful sense.

Selection used to be a first-match-wins ladder over ppm thresholds. It is now an explicit
weighted score (see SCORE_* below), so tuning is one table rather than five branches, and
every signal that moves a word is visible in the output CSV.

`confidence_tier` keeps its five original values so public/api/_lib.php TIERS and the
--v-{ext,dec,hist,abs} CSS tokens continue to work unchanged.

Usage:
    python make_shortlist.py                    # write both seams
    python make_shortlist.py --stats            # dry run, print counts only
    python make_shortlist.py --min-score 55     # tune the relevant/curiosity cut
    python make_shortlist.py --input path/in.csv --output path/out.csv
"""

import argparse
import csv
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

import simplemma

INPUT_CSV     = Path('data/processed/forgotten_words_diachronic.csv')
OUTPUT_CSV    = Path('data/processed/forgotten_words_shortlist.csv')
INFLECTED_DB  = Path('data/processed/inflected_forms.db')

CORPUS_VERDICTS = ('extinct', 'declining', 'historical_only')

EXCLUDED_POS = {
    'prefix', 'sufix', 'element de compunere',
    'nume propriu', 'siglă', 'abreviere', 'non-lexem',
}

# DEX register tags that mark a word as regional rather than simply old. These are the
# least interesting class for this project: a word that was only ever used in one valley
# is not a word Romanian forgot.
REGIONAL_TAGS = {
    'regional', 'dialectal',
    'Moldova', 'Muntenia', 'Oltenia', 'Transilvania', 'Banat', 'Bucovina',
    'Maramureș', 'Țara Românească', 'Țările Române', 'Dobrogea', 'Crișana',
}

ARCHAIC_TAGS = {'învechit', 'arhaizant', 'ieșit din uz', 'odinioară', 'rar', 'livresc'}

# `family_ratio` is the undivided word-family count over the disambiguated per-lemma one
# (see validate_diachronic.aggregate_loose). Measured over the 8,879-word candidate pool:
#   1x        7,645   treapăt, falanster, pulpană, târguială     — isolated, genuinely rare
#   1.5–4x      741   cotonogi, perpeli, costiș                  — mild
#   4–10x       267   pardosi, teși, decepționa, moșnean         — verb beside its participle
#   10–25x       99   fracționa, colbui, mierare                 — same
#   25–100x      74   justeță, acurateță, franțuzi               — archaic spelling of a live word
#   100x+        53   datoriu, uleu, acurateță, mieru            — same
# 25× is where "this verb has a common participle" turns into "this is just how people
# used to spell a word they still use".
FAMILY_RATIO_VARIANT = 25.0
FAMILY_RATIO_SOFT    = 4.0

# Caveat worth knowing: this catches only variants that *share an inflectional paradigm*.
# Phonetic respellings with unrelated paradigms (vivliotică/bibliotecă, tăligraf/telegraf)
# are invisible to it — those are caught instead by having no current dictionary.

# `absent` scores well below the corpus-attested verdicts on purpose: it means neither
# corpus saw the word, so DEX is making the claim alone. Those words are still wanted —
# `oțios` is one — but they should not outrank a word we can actually show fell out of use.
SCORE_VERDICT = {
    'extinct':         30,
    'historical_only': 30,
    'declining':       20,
    'absent':          12,
}

# An `absent` word must also be genuinely scarce in modern text. Without this, the
# verdict's own ceiling (MODERN_ALIVE_OCC = 2000) would let a word with 1,500 modern
# occurrences through on DEX evidence alone.
ABSENT_MAX_MODERN_OCC = 500

# Rarity in modern Romanian, from the disambiguated paradigm count.
SCORE_MODERN = [(1, 25), (20, 22), (100, 18), (500, 14), (1000, 8)]

# How strongly the word is attested in the historical corpus. This is the signal that
# separates a word Romanian actually used and dropped from a word that only ever existed
# in a dictionary: `politeță` occurs 143 times in Wikisource, `celșag` occurs 4. Without
# it the score rewards obscurity itself, and the top of the list fills with entries like
# `potricală`, `țarțam` and `sărciner` — rare, but never really in circulation.
SCORE_HIST = [(3, 0), (6, 3), (15, 8), (40, 14), (100, 20)]
# DEX frequency is a literary-prominence score, not a usage frequency: `zapciu` is 0.96
# while `internet` is 0.88. High values mean the word was once well established, which is
# exactly what separates "forgotten" from "never really used".
SCORE_DEX_FREQ = [(0.95, 20), (0.85, 17), (0.70, 13), (0.50, 8), (0.30, 4)]
SCORE_DICTS    = [(15, 12), (10, 10), (6, 8), (3, 5), (2, 3)]

SCORE_CURRENT_DICT = 13
# No bonus for having a definition (owner decision 2026-11-10; docs/eval/definition-bonus.md).
# 94% of the shortlist has one, so 5 points lifted nearly every word, and each definition
# scrape moved words between seams with no new corpus evidence (68 after the 2026-08-17
# merge). A definition is a display matter. RELEVANT_MIN_SCORE dropped by the same 5 points.
SCORE_HAS_DEF      = 0
PENALTY_FAMILY     = 8

# `regional_only` and `variant_like` deliberately carry **no score penalty**. They are
# editorial preferences, not evidence quality, and the UI hides them by default — so
# penalising them here too meant no such word could ever reach the relevant seam, and
# the "arată regionalisme" / "arată variante vechi" toggles had nothing to reveal. With
# the penalties gone, 399 regional and 77 variant words sit in the relevant seam, hidden
# until asked for. The score says how good the evidence is; the flags say what you would
# rather not look at, and you can change your mind about the second.

# Tuned by inspecting the seam at 76 / 82 / 88 / 92, when a definition still added 5 points;
# 87 is that 92 without the bonus. Measured on 2026-11-09 data it keeps every word that has a
# definition and adds 6 that have none. The tuning note, in the old units: below ~92 the relevant seam starts
# taking in dictionary-only curiosities (potricală, țarțam, sărciner) that were never in
# circulation. At 92 it holds ~2.3k words and reads like poronci, jeț, jiganie, iznoavă,
# vorovi, ciocoism, prepelicar, spoliație, poetastru.
RELEVANT_MIN_SCORE = 87

# Min dex_frequency for a word with no corpus signal at all to qualify. The old code had
# this as 0.70 in classify()'s signature and 0.85 on the CLI, so the gate moved depending
# on how you called it (audit_sample.py:38-40 worked around it). One value now.
DEX_FREQ_THRESHOLD = 0.85

TIER_ORDER = {
    'corpus_extinct':          0,
    'corpus_declining':        1,
    'corpus_historical_only':  2,
    'dex_invechit_absent':     3,
    'dex_absent_highfreq':     4,
}

OUT_FIELDS = [
    'word', 'dex_frequency', 'description', 'dex_pos',
    'verdict', 'log_ratio', 'rank_shift', 'hist_ppm', 'modern_ppm', 'subtitle_ppm',
    'hist_occ', 'hist_docs', 'modern_occ', 'modern_docs',
    'modern_occ_loose', 'family_ratio',
    'dex_register', 'dex_domain', 'dex_etymology',
    'confidence_tier', 'is_forgotten', 'has_definition', 'dict_count',
    'newest_dict_year', 'in_current_dict',
    'quality_score', 'seam', 'regional_only', 'variant_like', 'variant_of',
]


def _banded(value: float, bands: list[tuple[float, int]], default: int = 0) -> int:
    """First band whose ceiling the value is under wins; `default` if it is over them all."""
    for ceiling, points in bands:
        if value < ceiling:
            return points
    return default


def pos_excluded(dex_pos: str) -> bool:
    tags = {t.strip() for t in (dex_pos or '').split('|') if t.strip()}
    return bool(tags & EXCLUDED_POS)


def register_tags(row: dict) -> set[str]:
    return {t.strip() for t in (row.get('dex_register') or '').split('|') if t.strip()}


def is_regional_only(row: dict) -> bool:
    """Regional, and not *also* marked as old.

    `jamlă` is tagged `regional|învechit` — a word that was regional and has since died is
    still a forgotten word. `jbârc`, tagged only `regional`, is just a local term.
    """
    tags = register_tags(row)
    return bool(tags & REGIONAL_TAGS) and not (tags & ARCHAIC_TAGS)


def confidence_tier(row: dict) -> str | None:
    """The five original tier names, kept so the UI's TIERS map and CSS tokens still work."""
    verdict = row['verdict']
    if verdict in CORPUS_VERDICTS:
        return f'corpus_{verdict}'
    if verdict == 'absent':
        if 'învechit' in register_tags(row):
            return 'dex_invechit_absent'
        return 'dex_absent_highfreq'
    return None


def score(row: dict) -> int:
    """Weighted quality score, 0–100ish. Higher = better candidate for the relevant seam."""
    dex_freq   = float(row.get('dex_frequency') or 0)
    modern_occ = float(row.get('modern_occ') or 0)
    dict_count = float(row.get('dict_count') or 0)
    family     = float(row.get('family_ratio') or 1)

    total = SCORE_VERDICT.get(row['verdict'], 0)
    total += _banded(modern_occ, SCORE_MODERN, default=4)
    total += _banded(float(row.get('hist_occ') or 0), SCORE_HIST, default=25)
    total += _banded(-dex_freq, [(-c, p) for c, p in SCORE_DEX_FREQ], default=0)
    total += _banded(-dict_count, [(-c, p) for c, p in SCORE_DICTS], default=0)

    if str(row.get('in_current_dict')) == '1':
        total += SCORE_CURRENT_DICT
    if str(row.get('has_definition')) == '1':
        total += SCORE_HAS_DEF
    # A moderate family ratio (4–25×) is an evidence problem, not a preference: the
    # lemma's own count is being propped up by relatives, so trust it less. Above 25×
    # `variant_like` takes over, and that is the UI's call rather than the score's.
    if FAMILY_RATIO_SOFT <= family < FAMILY_RATIO_VARIANT:
        total -= PENALTY_FAMILY
    return max(0, total)


def eligible(row: dict, exclude_etym: frozenset, dex_freq_threshold: float) -> bool:
    """Hard gates. A word failing any of these is not a candidate at all."""
    if pos_excluded(row.get('dex_pos', '')):
        return False
    if exclude_etym:
        etym = {t.strip() for t in (row.get('dex_etymology') or '').split('|') if t.strip()}
        if etym & exclude_etym:
            return False
    if float(row.get('dex_frequency') or 0) >= 1.0:
        return False                      # core DEX vocabulary
    verdict = row['verdict']
    if verdict in CORPUS_VERDICTS:
        return True
    if verdict == 'absent':
        # No corpus signal either way, so DEX has to carry the claim on its own: either it
        # marks the word obsolete, or it is prominent enough that its total absence from
        # 17B tokens of modern text is itself the finding (this is the `oțios` case).
        if float(row.get('modern_occ') or 0) >= ABSENT_MAX_MODERN_OCC:
            return False
        if 'învechit' in register_tags(row):
            return True
        return float(row.get('dex_frequency') or 0) >= dex_freq_threshold
    return False                          # alive / emerging


def load_variant_map(db_path: Path) -> dict[str, str]:
    """{lemma: the most common other lemma it shares a surface form with}.

    Lets the UI say *which* current word an archaic spelling shadows ("politeță →
    politețe") rather than only that it shadows one. Optional: returns {} if the DB is
    missing, and `variant_of` is then left blank.
    """
    if not db_path.exists():
        return {}
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            'SELECT form, lemma FROM form_lemma WHERE n_lemmas > 1').fetchall()
        freq = dict(conn.execute(
            'SELECT lemma, MAX(frequency) FROM lexeme GROUP BY lemma').fetchall())
    except sqlite3.OperationalError:
        return {}
    finally:
        conn.close()

    by_form: dict[str, list[str]] = defaultdict(list)
    for form, lemma in rows:
        by_form[form].append(lemma)

    best: dict[str, tuple[float, str]] = {}
    for lemmas in by_form.values():
        for lemma in lemmas:
            for other in lemmas:
                if other == lemma:
                    continue
                f = freq.get(other) or 0
                if f > best.get(lemma, (-1, ''))[0]:
                    best[lemma] = (f, other)
    return {lemma: other for lemma, (_f, other) in best.items()}


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Score the diachronic results and split them into two seams')
    parser.add_argument('--input',  type=Path, default=INPUT_CSV)
    parser.add_argument('--output', type=Path, default=OUTPUT_CSV,
                        help='Combined output; the seam is a column (default: %(default)s)')
    parser.add_argument('--limit',  type=int,  default=None, help='Cap total output rows')
    parser.add_argument('--stats',  action='store_true', help='Print stats only, do not write')
    parser.add_argument(
        '--exclude-etymology', default='', metavar='TAGS',
        help='Comma-separated etymology tags to exclude. E.g. anglicism,franțuzism')
    parser.add_argument(
        '--dex-freq-threshold', type=float, default=DEX_FREQ_THRESHOLD, metavar='FREQ',
        help='Min dex_frequency for a no-corpus-signal word to qualify (default: %(default)s)')
    parser.add_argument(
        '--min-score', type=int, default=RELEVANT_MIN_SCORE, metavar='N',
        help='Score at or above which a word joins the relevant seam (default: %(default)s)')
    parser.add_argument(
        '--no-dedup', action='store_true',
        help='Skip simplemma lemma deduplication (keep all inflected forms separately)')
    args = parser.parse_args()

    exclude_etym = frozenset(
        t.strip() for t in args.exclude_etymology.split(',') if t.strip())

    if not args.input.exists():
        print(f'Missing: {args.input}  — run validate_diachronic.py first.')
        return 1

    rows = list(csv.DictReader(args.input.open(encoding='utf-8')))
    print(f'Read {len(rows):,} rows from {args.input}')

    variant_of = load_variant_map(INFLECTED_DB)
    if variant_of:
        print(f'  {len(variant_of):,} lemmas share a form with another lemma')

    selected: list[dict] = []
    dropped = Counter()
    for row in rows:
        if pos_excluded(row.get('dex_pos', '')):
            dropped['pos'] += 1
            continue
        if not eligible(row, exclude_etym, args.dex_freq_threshold):
            dropped[row['verdict'] if row['verdict'] in ('alive', 'emerging')
                    else 'not eligible'] += 1
            continue
        tier = confidence_tier(row)
        if tier is None:
            dropped['no tier'] += 1
            continue

        family = float(row.get('family_ratio') or 1)
        regional = is_regional_only(row)
        variant = family >= FAMILY_RATIO_VARIANT
        s = score(row)

        out = {f: row.get(f, '') for f in OUT_FIELDS}
        out['confidence_tier'] = tier
        out['is_forgotten']    = 'true'
        out['quality_score']   = s
        out['regional_only']   = 1 if regional else 0
        out['variant_like']    = 1 if variant else 0
        out['variant_of']      = variant_of.get(row['word'], '') if variant else ''
        # The seam is decided by score alone. `regional_only` and `variant_like` already
        # cost the score 25 and 35 points, so they rarely clear the bar anyway — and
        # excluding them here *as well* made the UI's "arată regionalisme" / "arată
        # variante vechi" toggles dead controls, because the relevant seam then contained
        # nothing for them to reveal. Hiding those words is the UI's job, and the UI can
        # be argued with.
        out['seam'] = 'relevant' if s >= args.min_score else 'curiosity'
        selected.append(out)

    def sort_key(r: dict):
        return (0 if r['seam'] == 'relevant' else 1,
                -int(r['quality_score']),
                TIER_ORDER.get(r['confidence_tier'], 99),
                -float(r['dex_frequency'] or 0))

    selected.sort(key=sort_key)

    # Lemma deduplication: collapse inflected/derived forms to their canonical lemma.
    # Covers regular inflections (murea→muri) but NOT verb-derived nouns/adjectives
    # (bleui/bleuire/bleuit stay separate — a known simplemma gap).
    if not args.no_dedup:
        groups: dict[str, list[dict]] = defaultdict(list)
        for row in selected:
            groups[simplemma.lemmatize(row['word'], lang='ro')].append(row)
        deduped, n_removed = [], 0
        for lem, group in groups.items():
            canonical = next((r for r in group if r['word'] == lem), group[0])
            deduped.append(canonical)
            n_removed += len(group) - 1
        deduped.sort(key=sort_key)
        selected = deduped
        if n_removed:
            print(f'  Lemma dedup: collapsed {n_removed:,} inflected forms')

    if args.limit:
        selected = selected[:args.limit]

    seams = Counter(r['seam'] for r in selected)
    tiers = Counter(r['confidence_tier'] for r in selected)
    print()
    for seam in ('relevant', 'curiosity'):
        print(f'  {seam:<28} {seams[seam]:>6,}')
    print(f'  {"-" * 35}')
    print(f'  {"Total":<28} {len(selected):>6,}')
    print()
    for tier in sorted(tiers, key=lambda t: TIER_ORDER.get(t, 99)):
        print(f'  {tier:<28} {tiers[tier]:>6,}')
    print()
    for reason, n in dropped.most_common():
        print(f'  dropped ({reason:<18}) {n:>6,}')

    if args.stats:
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=OUT_FIELDS)
        writer.writeheader()
        writer.writerows(selected)

    print(f'\nWritten → {args.output}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
