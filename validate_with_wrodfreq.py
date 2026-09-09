#!/usr/bin/env python3
"""
Validate DEX forgotten-word candidates against wROdfreq — the sibling project
at ../gov2/wrodfreq, a Romanian word-frequency table built from 5 open
corpora (23.5B+2.19B+1.94B+109.6M+84.4M tokens: web, news, subtitles,
Wikipedia, Europarl/DGT). See docs/wordfreq-recipe.md §4 and CLAUDE.md's
`Lexeme.frequency` note for why this exists as a *second*, parallel screen
rather than a patch to validate_with_wordfreq.py:

wordfreq measured 99.6% of the 60,000-candidate shortlist at exactly zipf=0
(CLAUDE.md, 2026-08-11) — its Romanian coverage is too thin to resolve
"forgotten" from "just uncommon" at the low end, which is why that screen's
`rare_in_use` tab was disconnected. wROdfreq exists specifically to fix that
resolution problem: measured here on a random 2,000-word sample of the real
18,271-word shortlist, only 27.8% come back at zipf=0 — a random sample from
the same *screen*, not from wROdfreq's own general vocabulary, so this
number is about this actual problem, not a favorable cherry-pick.

Same three tiers as validate_with_wordfreq.py (forgotten / rare_in_use /
common) and the same default thresholds (3.0 / 3.5), kept for continuity —
but these were *calibrated for wordfreq's Zipf distribution*
(CLAUDE.md: the 3.5 upper threshold was measured against real words that
opened the tier at 4.5). wROdfreq's own floors run lower (`web`'s reliability
floor is -0.67 Zipf, driven by its 23.5B-token size — see spec §8.1), so its
Zipf values for the same word are not guaranteed to line up with wordfreq's
on the same numeric scale. Treat these two defaults as a starting point for
recalibration against wROdfreq's actual distribution, not an assumption that
they still mean the same thing here — this script does not attempt that
recalibration itself.

**New columns wordfreq could never provide** (spec §8.3 — this is the
`n_reliable` "expose it as a corroboration signal" spec asks for, M7):

  n_reliable    how many of wROdfreq's 5 independent modern corpora measured
                this word above their own reliability floor — a corroboration
                count, not an average. "Absent from 5 independent corpora" is
                a stronger claim than "absent from 1" even when neither can
                say a precise rate (spec §8.1's abstention rule: a source
                that never saw a word contributes nothing, not a zero).
  n_attesting   how many saw it at all, even below their floor — the "exists
                but is rare" band between this and n_reliable.
  spread        how much the reliable sources disagree (zipf_max - zipf_min)
                — register-bound or diachronically shifting words show up
                here; not meaningful validation signal on its own, but
                worth carrying through for anyone inspecting a row by hand.

No `--lemmatize`/simplemma dependency, unlike the wordfreq screen: wROdfreq's
own surface-form coverage (~6.2M words vs wordfreq's ~43k) makes a lemmatizer
pass less necessary, and simplemma had a documented failure mode this avoids
by construction — picking the wrong homograph lemma (`secret` → `secreta`,
`dor` → `durea`). The paradigm-max rollup below (mirroring
validate_with_wordfreq.py's own `paradigm_zipf`) still runs directly off
DEX's own inflected_forms.db paradigm, keyed on the headword, never a
lemmatizer's guess.

Usage:
    python validate_with_wrodfreq.py
    python validate_with_wrodfreq.py --threshold 2.5 --upper-threshold 4.0
    python validate_with_wrodfreq.py --keep-all
    python validate_with_wrodfreq.py -i path/in.csv -o path/out.csv
"""

import argparse
import csv
import sqlite3
import sys
import unicodedata
from pathlib import Path

WRODFREQ_PATH = Path(__file__).resolve().parent.parent / "gov2" / "wrodfreq"

# Same markers, same reasoning as validate_with_wordfreq.py's
# ARCHAIC_REGISTER_MARKERS — kept identical so the two screens' rare_in_use
# tiers are comparable side by side.
ARCHAIC_REGISTER_MARKERS = frozenset({
    'învechit',
    'arhaizant',
    'rar',
    'ieșit din uz',
})

INFLECTED_DB = Path('data/processed/inflected_forms.db')


def normalize_romanian(text: str) -> str:
    """Lowercase + cedilla→comma + NFC. Mirrors wrodfreq.tokenizer.normalize
    (and validate_with_wordfreq.py's own copy) — same normalization, so a
    word looked up here and in that screen resolves to the same key."""
    return unicodedata.normalize(
        'NFC',
        text.lower().replace('ş', 'ș').replace('ţ', 'ț'),
    )


def paradigm_detail(word: str, conn, frequency_detail_fn, cache: dict):
    """The wROdfreq FrequencyDetail for whichever form of word's DEX paradigm
    has the highest zipf, or None if DEX has no paradigm for it and the
    citation form itself isn't in wROdfreq either.

    Mirrors validate_with_wordfreq.py's paradigm_zipf(): max rather than sum
    or mean, because this asks "is any form of this word in current use?",
    a presence question, not a rate estimate — summing a log scale across
    forms would mean nothing. Max also naturally carries that form's own
    n_reliable/n_attesting/spread along with its zipf, so the corroboration
    signal is for the same form the tier decision is based on.
    """
    if word in cache:
        return cache[word]
    rows = conn.execute(
        """SELECT i.form FROM lexeme l
             JOIN inflected i ON i.lexeme_id = l.lexeme_id
            WHERE l.lemma = ?""",
        (word,),
    ).fetchall()
    forms = {normalize_romanian(f) for (f,) in rows if f}
    forms.add(word)  # citation form itself, in case DEX has no paradigm rows for it
    best = None
    for f in forms:
        d = frequency_detail_fn(f)
        if d is not None and (best is None or d.zipf > best.zipf):
            best = d
    cache[word] = best
    return best


def has_archaic_register(dex_register: str) -> bool:
    """True if the semicolon-joined dex_register contains an archaic/rare marker."""
    if not dex_register:
        return False
    tokens = {normalize_romanian(t.strip()) for t in dex_register.split(';')}
    return bool(tokens & ARCHAIC_REGISTER_MARKERS)


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Filter DEX forgotten-word candidates with wROdfreq.',
    )
    parser.add_argument(
        '-i', '--input',
        type=Path,
        default=Path('data/processed/forgotten_words_curated.csv'),
        help='Curated candidates CSV (default: %(default)s)',
    )
    parser.add_argument(
        '-o', '--output',
        type=Path,
        default=Path('data/processed/forgotten_words_validated_wrodfreq.csv'),
        help='Output CSV for forgotten words (default: %(default)s)',
    )
    parser.add_argument(
        '--output-rare',
        type=Path,
        default=Path('data/processed/rare_words_wrodfreq.csv'),
        help='Output CSV for rare-in-use words; ignored with --keep-all '
             '(default: %(default)s)',
    )
    parser.add_argument(
        '-t', '--threshold',
        type=float,
        default=3.0,
        help='Lower Zipf threshold; rows with zipf < threshold are "forgotten" '
             '(default: %(default)s — carried over from validate_with_wordfreq.py, '
             'not recalibrated for wROdfreq\'s own Zipf distribution, see module docstring)',
    )
    parser.add_argument(
        '--upper-threshold',
        type=float,
        default=3.5,
        help='Upper Zipf threshold; rows with zipf >= this are filtered as '
             'common. Between threshold and upper-threshold = "rare_in_use" '
             '(default: %(default)s, same caveat as --threshold)',
    )
    parser.add_argument(
        '--keep-all',
        action='store_true',
        help='Annotate every row with tier and write to main output instead '
             'of filtering (useful for inspection; --output-rare is ignored)',
    )
    parser.add_argument(
        '--rare-register',
        choices=('archaic', 'any'),
        default='archaic',
        help='Which dex_register tags qualify a word for the rare_in_use tier: '
             '"archaic" (default) requires an archaic/rare marker '
             f'({", ".join(sorted(ARCHAIC_REGISTER_MARKERS))}) so the tier is not '
             'polluted by modern loanwords; "any" admits any non-empty register '
             '(legacy behaviour).',
    )
    parser.add_argument(
        '--dedup',
        action=argparse.BooleanOptionalAction,
        default=True,
        help='Collapse rows sharing a word_no_accent to the first seen, so the '
             'same headword does not appear once per part-of-speech '
             '(default: enabled)',
    )
    args = parser.parse_args()

    try:
        import wrodfreq
    except ImportError:
        print(f'wrodfreq not installed. Run: pip install -e {WRODFREQ_PATH}',
              file=sys.stderr)
        return 1

    if not args.input.exists():
        print(f'Input not found: {args.input}', file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)

    infl_conn = None
    if INFLECTED_DB.exists():
        infl_conn = sqlite3.connect(f'file:{INFLECTED_DB}?mode=ro', uri=True)
    else:
        print(f'! {INFLECTED_DB} not found — tiering on the citation form alone, which '
              f'calls common verbs rare. Run extract_inflected_forms.py.', file=sys.stderr)
    para_cache: dict[str, object] = {}

    rows_in = 0
    counts = {'forgotten': 0, 'rare_in_use': 0, 'common': 0}
    zero_zipf = 0
    deduped = 0
    seen_words: set[str] = set()

    def _run(fout, frare):
        nonlocal rows_in, zero_zipf, deduped
        reader = csv.DictReader(fin)
        if not reader.fieldnames or 'word' not in reader.fieldnames:
            print(f'Input has no "word" column: {args.input}', file=sys.stderr)
            return 1
        other_fields = [f for f in reader.fieldnames if f != 'word']
        out_fields = other_fields + [
            'zipf_frequency', 'n_reliable', 'n_attesting', 'n_sources', 'spread',
            'tier', 'is_forgotten', 'word',
        ]
        writer = csv.DictWriter(fout, fieldnames=out_fields)
        writer.writeheader()
        if frare is not None:
            writer_rare = csv.DictWriter(frare, fieldnames=out_fields)
            writer_rare.writeheader()
        else:
            writer_rare = None

        for row in reader:
            rows_in += 1
            raw = row.get('word_no_accent') or row.get('word', '')
            word = normalize_romanian(raw)
            if not word:
                continue
            if args.dedup:
                if word in seen_words:
                    deduped += 1
                    continue
                seen_words.add(word)

            detail = wrodfreq.frequency_detail(word)
            zipf = detail.zipf if detail is not None else 0.0
            if zipf == 0.0:
                zero_zipf += 1

            if args.rare_register == 'archaic':
                register_ok = has_archaic_register(row.get('dex_register', ''))
            else:
                register_ok = bool((row.get('dex_register') or '').strip())

            # Same lazy-evaluation shape as validate_with_wordfreq.py's
            # paradigm_zipf call: only rows that already clear the floor and
            # carry an archaic register walk the paradigm table.
            if zipf < args.threshold:
                tier = 'forgotten'
            elif register_ok:
                para = (paradigm_detail(word, infl_conn, wrodfreq.frequency_detail, para_cache)
                        if infl_conn else None)
                usage = para.zipf if para is not None else zipf
                if para is not None:
                    detail = para  # report the paradigm-winning form's corroboration, not the headword's
                tier = 'rare_in_use' if usage < args.upper_threshold else 'common'
            else:
                tier = 'common'

            counts[tier] += 1
            row['zipf_frequency'] = f'{zipf:.3f}'
            row['n_reliable'] = detail.n_reliable if detail is not None else 0
            row['n_attesting'] = detail.n_attesting if detail is not None else 0
            row['n_sources'] = detail.n_sources if detail is not None else ''
            row['spread'] = f'{detail.spread:.3f}' if detail is not None else ''
            row['tier'] = tier
            row['is_forgotten'] = str(tier == 'forgotten').lower()

            if args.keep_all:
                writer.writerow(row)
            elif tier == 'forgotten':
                writer.writerow(row)
            elif tier == 'rare_in_use' and writer_rare is not None:
                writer_rare.writerow(row)

        return 0

    with args.input.open('r', encoding='utf-8') as fin, \
         args.output.open('w', encoding='utf-8', newline='') as fout:
        if args.keep_all:
            rc = _run(fout, frare=None)
        else:
            args.output_rare.parent.mkdir(parents=True, exist_ok=True)
            with args.output_rare.open('w', encoding='utf-8', newline='') as frare:
                rc = _run(fout, frare)

    if rc != 0:
        return rc

    pct_forgotten = (counts['forgotten'] / rows_in * 100) if rows_in else 0.0
    pct_rare = (counts['rare_in_use'] / rows_in * 100) if rows_in else 0.0
    print(f'Read        : {rows_in:,} candidates')
    if args.dedup:
        print(f'Deduped     : {deduped:,} dropped (same word_no_accent)')
    print(f'Forgotten   : {counts["forgotten"]:,} ({pct_forgotten:.1f}%) zipf < {args.threshold}')
    print(f'Rare in use : {counts["rare_in_use"]:,} ({pct_rare:.1f}%) '
          f'{args.threshold} ≤ zipf < {args.upper_threshold}')
    print(f'Common      : {counts["common"]:,} filtered out')
    print(f'Zero Zipf   : {zero_zipf:,} (no signal in any wROdfreq source) '
          f'({100*zero_zipf/rows_in:.1f}%)')
    print(f'Output      : {args.output}')
    if not args.keep_all:
        print(f'Rare output : {args.output_rare}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
