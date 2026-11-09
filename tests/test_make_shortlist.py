import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import make_shortlist as ms


def make_diachronic_csv(path: Path, rows: list[dict]) -> None:
    fields = [
        'word', 'dex_frequency', 'description', 'rarity_category',
        'hist_occurrences', 'hist_documents', 'hist_ppm',
        'modern_occurrences', 'modern_documents', 'modern_ppm',
        'hist_occ', 'hist_docs', 'modern_occ', 'modern_docs',
        'modern_occ_loose', 'family_ratio', 'rank_shift',
        'log_ratio', 'verdict',
        'dex_pos', 'dex_register', 'dex_domain', 'dex_etymology',
        'has_definition', 'dict_count', 'newest_dict_year', 'in_current_dict',
    ]
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in rows:
            w.writerow({f: row.get(f, '') for f in fields})


# A strong `relevant` candidate: real historical footing, near-absent today, broadly
# attested, still in a current dictionary, no regional or variant baggage.
BASE_ROW = {
    'word': 'ajutoriu',
    'dex_frequency': '0.90',
    'description': 'adj.',
    'rarity_category': 'rare',
    'hist_occurrences': '120', 'hist_documents': '40', 'hist_ppm': '1.2',
    'modern_occurrences': '10', 'modern_documents': '5', 'modern_ppm': '0.0',
    'hist_occ': '120', 'hist_docs': '40', 'modern_occ': '10', 'modern_docs': '5',
    'modern_occ_loose': '10', 'family_ratio': '1.00', 'rank_shift': '0.30',
    'log_ratio': '3.5',
    'verdict': 'historical_only',
    'dex_pos': 'adjectiv',
    'dex_register': '', 'dex_domain': '', 'dex_etymology': 'slavă',
    'has_definition': '1', 'dict_count': '16',
    'newest_dict_year': '2021', 'in_current_dict': '1',
}

ANGLICISM_ROW = {**BASE_ROW, 'word': 'sendviș', 'dex_etymology': 'anglicism'}

ABSENT_ROW = {
    **BASE_ROW,
    'word': 'lăut',
    'verdict': 'absent',
    'hist_occ': '0', 'hist_docs': '0', 'hist_ppm': '0.0',
    'modern_occ': '0', 'modern_ppm': '0.0',
    'dex_register': 'învechit',
    'dex_etymology': '',
}


def run(inp: Path, out: Path, *extra: str) -> list[dict]:
    sys.argv = ['make_shortlist.py', '--input', str(inp), '--output', str(out), *extra]
    ms.main()
    return list(csv.DictReader(out.open(encoding='utf-8')))


# ── Pass-through ──────────────────────────────────────────────────────────────

def test_has_definition_in_out_fields():
    assert 'has_definition' in ms.OUT_FIELDS


def test_has_definition_passes_through_to_output(tmp_path):
    make_diachronic_csv(tmp_path / 'in.csv', [BASE_ROW])
    rows = run(tmp_path / 'in.csv', tmp_path / 'out.csv')
    assert len(rows) == 1
    assert rows[0]['has_definition'] == '1'


# ── Hard gates ────────────────────────────────────────────────────────────────

def test_eligible_excludes_matching_etymology():
    assert not ms.eligible(ANGLICISM_ROW, frozenset({'anglicism'}), 0.85)


def test_eligible_keeps_non_matching_etymology():
    assert ms.eligible(BASE_ROW, frozenset({'anglicism'}), 0.85)


def test_eligible_drops_alive_words():
    """The whole point of the rescore: a word in use today is not a candidate."""
    assert not ms.eligible({**BASE_ROW, 'verdict': 'alive'}, frozenset(), 0.85)
    assert not ms.eligible({**BASE_ROW, 'verdict': 'emerging'}, frozenset(), 0.85)


def test_eligible_drops_core_vocabulary():
    assert not ms.eligible({**BASE_ROW, 'dex_frequency': '1.0'}, frozenset(), 0.85)


def test_eligible_absent_needs_dex_evidence():
    plain = {**ABSENT_ROW, 'dex_register': '', 'dex_frequency': '0.40'}
    assert not ms.eligible(plain, frozenset(), 0.85)
    assert ms.eligible(ABSENT_ROW, frozenset(), 0.85)              # învechit carries it
    assert ms.eligible({**plain, 'dex_frequency': '0.90'}, frozenset(), 0.85)


def test_eligible_absent_rejects_words_still_common():
    """`absent` tops out at MODERN_ALIVE_OCC, so it must be floored separately."""
    busy = {**ABSENT_ROW, 'modern_occ': str(ms.ABSENT_MAX_MODERN_OCC + 1)}
    assert not ms.eligible(busy, frozenset(), 0.85)


def test_pos_excluded():
    assert ms.pos_excluded('adjectiv|prefix')
    assert not ms.pos_excluded('adjectiv|substantiv feminin')


# ── Tier names the UI depends on ──────────────────────────────────────────────

def test_confidence_tier_keeps_ui_vocabulary():
    """public/api/_lib.php TIERS and the --v-* CSS tokens key off these five strings."""
    assert ms.confidence_tier({**BASE_ROW, 'verdict': 'extinct'}) == 'corpus_extinct'
    assert ms.confidence_tier({**BASE_ROW, 'verdict': 'declining'}) == 'corpus_declining'
    assert ms.confidence_tier(BASE_ROW) == 'corpus_historical_only'
    assert ms.confidence_tier(ABSENT_ROW) == 'dex_invechit_absent'
    assert ms.confidence_tier(
        {**ABSENT_ROW, 'dex_register': ''}) == 'dex_absent_highfreq'


# ── Regional / variant handling ───────────────────────────────────────────────

def test_regional_only_requires_absence_of_an_archaic_tag():
    """`regional|învechit` is a word that died; plain `regional` is just a local term."""
    assert ms.is_regional_only({**BASE_ROW, 'dex_register': 'regional'})
    assert ms.is_regional_only({**BASE_ROW, 'dex_register': 'Moldova'})
    assert not ms.is_regional_only({**BASE_ROW, 'dex_register': 'regional|învechit'})
    assert not ms.is_regional_only(BASE_ROW)


def test_regional_word_is_flagged_not_demoted(tmp_path):
    """The flag is the UI's to act on. Demoting the word here too would leave the
    `show_regional` toggle with nothing to reveal."""
    make_diachronic_csv(tmp_path / 'in.csv',
                        [BASE_ROW, {**BASE_ROW, 'word': 'jbârc',
                                    'dex_register': 'regional'}])
    rows = {r['word']: r for r in run(tmp_path / 'in.csv', tmp_path / 'out.csv')}
    assert rows['jbârc']['regional_only'] == '1'
    assert rows['ajutoriu']['regional_only'] == '0'
    assert rows['jbârc']['seam'] == rows['ajutoriu']['seam']


def test_archaic_variant_is_flagged_with_its_counterpart(tmp_path):
    """A high family_ratio means the word survives as a relative of a current one."""
    variant = {**BASE_ROW, 'word': 'politeță',
               'modern_occ_loose': '33458', 'family_ratio': '60.00'}
    make_diachronic_csv(tmp_path / 'in.csv', [BASE_ROW, variant])
    rows = {r['word']: r for r in run(tmp_path / 'in.csv', tmp_path / 'out.csv')}
    assert rows['politeță']['variant_like'] == '1'
    assert rows['ajutoriu']['variant_like'] == '0'


def test_verb_beside_its_participle_is_not_called_a_variant(tmp_path):
    """posomorî sits at ~8x — a common participle, not an archaic spelling."""
    verb = {**BASE_ROW, 'word': 'posomorî', 'family_ratio': '8.00'}
    make_diachronic_csv(tmp_path / 'in.csv', [verb])
    rows = run(tmp_path / 'in.csv', tmp_path / 'out.csv')
    assert rows[0]['variant_like'] == '0'


# ── Scoring ───────────────────────────────────────────────────────────────────

def test_historical_attestation_outranks_bare_obscurity():
    """The signal that keeps dictionary-only curiosities off the top of the list."""
    attested = {**BASE_ROW, 'hist_occ': '143'}
    barely   = {**BASE_ROW, 'hist_occ': '4'}
    assert ms.score(attested) > ms.score(barely)


def test_current_dictionary_raises_score():
    assert ms.score(BASE_ROW) > ms.score({**BASE_ROW, 'in_current_dict': '0'})


def test_a_definition_adds_no_points():
    """Owner decision 2026-11-10 (docs/eval/definition-bonus.md). A definition is a display
    matter; scoring it let every definition scrape move words between seams."""
    assert ms.score({**BASE_ROW, 'has_definition': '0'}) == ms.score(BASE_ROW)


def test_a_definition_scrape_cannot_change_the_seam(tmp_path):
    rows = [{**BASE_ROW, 'word': 'cudef'}, {**BASE_ROW, 'word': 'faradef', 'has_definition': '0'}]
    make_diachronic_csv(tmp_path / 'in.csv', rows)
    out = {r['word']: r for r in run(tmp_path / 'in.csv', tmp_path / 'out.csv', '--no-dedup')}
    assert out['cudef']['seam'] == out['faradef']['seam']
    assert out['cudef']['quality_score'] == out['faradef']['quality_score']
    assert ms.RELEVANT_MIN_SCORE == 87     # the former 92 minus the former 5-point bonus


def test_regional_and_variant_carry_no_score_penalty():
    """Evidence quality and editorial preference are kept apart. Penalising these here
    as well as hiding them in the UI meant no such word could reach the relevant seam,
    so the toggles that are supposed to bring them back had nothing to bring."""
    assert ms.score({**BASE_ROW, 'dex_register': 'regional'}) == ms.score(BASE_ROW)
    assert ms.score({**BASE_ROW, 'family_ratio': '60'}) == ms.score(BASE_ROW)


def test_moderate_family_ratio_still_costs_score():
    """4–25× is an evidence problem — the lemma's count is propped up by relatives."""
    assert ms.score({**BASE_ROW, 'family_ratio': '8'}) < ms.score(BASE_ROW)


def test_seams_are_disjoint_and_labelled(tmp_path):
    make_diachronic_csv(tmp_path / 'in.csv', [
        BASE_ROW,
        {**BASE_ROW, 'word': 'jbârc', 'dex_register': 'regional'},
        {**BASE_ROW, 'word': 'politeță', 'family_ratio': '60.00'},
    ])
    rows = run(tmp_path / 'in.csv', tmp_path / 'out.csv')
    assert {r['seam'] for r in rows} <= {'relevant', 'curiosity'}
    relevant = {r['word'] for r in rows if r['seam'] == 'relevant'}
    curiosity = {r['word'] for r in rows if r['seam'] == 'curiosity'}
    assert relevant & curiosity == set()


# ── CLI ───────────────────────────────────────────────────────────────────────

def test_exclude_etymology_cli_filters_output(tmp_path):
    make_diachronic_csv(tmp_path / 'in.csv', [BASE_ROW, ANGLICISM_ROW])
    rows = run(tmp_path / 'in.csv', tmp_path / 'out.csv',
               '--exclude-etymology', 'anglicism')
    words = [r['word'] for r in rows]
    assert 'ajutoriu' in words
    assert 'sendviș' not in words


def test_dex_freq_threshold_has_a_single_source():
    """It used to be 0.70 in classify()'s signature and 0.85 on the CLI, so the gate
    moved depending on how you called it (audit_sample.py:38-40 worked around it).
    The CLI default is now wired to the constant rather than a second literal."""
    assert ms.DEX_FREQ_THRESHOLD == 0.85
    src = Path(ms.__file__).read_text(encoding='utf-8')
    assert 'default=DEX_FREQ_THRESHOLD' in src
