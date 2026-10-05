"""F08 — the UI database build publishes only validated, complete databases.

Every test builds from a tiny synthetic shortlist into tmp_path, with its own registry.
Nothing here reads or writes public/data/ui.db, data/word_ids.tsv or data/processed/.
"""
import hashlib
import multiprocessing
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT))
import build_ui_db as B  # noqa: E402
import word_ids  # noqa: E402

HEADER = 'word,dex_frequency,verdict,seam,quality_score,definition\n'


def shortlist(tmp_path, words, name='shortlist.csv'):
    p = tmp_path / name
    p.write_text(HEADER + ''.join(f'{w},0.5,absent,relevant,100,\n' for w in words),
                 encoding='utf-8')
    return p


def inputs(tmp_path):
    """Every optional/required input points at a missing file inside tmp_path."""
    d = tmp_path / 'none'
    return B.Inputs(web=d / 'web', defs=d / 'defs', dict_sources=d / 'ds', synonyms=d / 'syn',
                    meanings=d / 'mean', lexemes=d / 'lex', freq=d / 'freq',
                    inflected=d / 'infl', editorial=d / 'editorial.tsv')


def run_build(tmp_path, words, out=None, reg=None, **kw):
    out = out or tmp_path / 'out' / 'ui.db'
    reg = reg or tmp_path / 'reg' / 'word_ids.tsv'
    kw.setdefault('min_words', 1)
    kw.setdefault('allow_missing_inputs', True)
    B.build(shortlist(tmp_path, words), None, None, None, out,
            inputs=inputs(tmp_path), registry_path=reg, **kw)
    return out, reg


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def listing(directory):
    return sorted(p.name for p in Path(directory).iterdir())


def ids(db):
    c = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
    try:
        return dict(c.execute('SELECT word, word_id FROM words'))
    finally:
        c.close()


@pytest.fixture
def good(tmp_path):
    out, reg = run_build(tmp_path, ['alfa', 'beta', 'gamă'])
    return tmp_path, out, reg


# ---- success ------------------------------------------------------------------------

def test_success_is_complete_and_selfcontained(good):
    tmp_path, out, reg = good
    c = sqlite3.connect(f'file:{out}?mode=ro', uri=True)
    assert c.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    assert c.execute('PRAGMA journal_mode').fetchone()[0] == 'delete'
    cols = {r[1] for r in c.execute('PRAGMA table_info(words)')}
    assert set(B.REQUIRED_WORD_COLUMNS) == cols
    c.close()
    # Only the database and the lock file remain beside it; no sidecars, no temps.
    assert listing(out.parent) == ['ui.db', 'ui.db.lock']
    assert ids(out) == word_ids.load_registry(reg)


def test_rebuild_preserves_ids_and_appends_only_new_words(good):
    tmp_path, out, reg = good
    before = ids(out)
    run_build(tmp_path, ['alfa', 'beta', 'gamă', 'delta'], out=out, reg=reg)
    after = ids(out)
    assert {w: i for w, i in after.items() if w in before} == before
    assert after['delta'] == max(before.values()) + 1
    # A word that left the shortlist keeps its registry id.
    run_build(tmp_path, ['alfa'], out=out, reg=reg, allow_shrink=True)
    assert word_ids.load_registry(reg)['delta'] == after['delta']
    assert set(ids(out)) == {'alfa'}


def test_identical_second_build_appends_nothing(good):
    tmp_path, out, reg = good
    reg_bytes = reg.read_bytes()
    run_build(tmp_path, ['alfa', 'beta', 'gamă'], out=out, reg=reg)
    assert reg.read_bytes() == reg_bytes


# ---- failure injection --------------------------------------------------------------

def _assert_untouched(out, before_digest, before_listing):
    assert digest(out) == before_digest
    assert listing(out.parent) == before_listing
    c = sqlite3.connect(f'file:{out}?mode=ro', uri=True)
    assert c.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    assert c.execute('SELECT COUNT(*) FROM words').fetchone()[0] == 3
    c.close()


class Boom(Exception):
    pass


def _boom(*a, **k):
    raise Boom('injected')


@pytest.mark.parametrize('target', [
    'merge_dict_sources',      # enrichment
    'merge_synonyms',          # enrichment
    'mark_deverbal_nouns',     # enrichment (mark step)
    '_apply_word_ids',         # id assignment
    'finalize_candidate',      # checkpoint / journal switch
    'validate_candidate',      # validation
    '_bool',                   # row loading
])
def test_failure_keeps_previous_output(good, monkeypatch, target):
    tmp_path, out, reg = good
    snap = (digest(out), listing(out.parent))
    monkeypatch.setattr(B, target, _boom)
    with pytest.raises(Boom):
        run_build(tmp_path, ['alfa', 'beta', 'gamă', 'delta'], out=out, reg=reg)
    _assert_untouched(out, *snap)


def test_failed_build_leaves_registry_appended_only(good, monkeypatch):
    tmp_path, out, reg = good
    old = reg.read_text(encoding='utf-8')
    monkeypatch.setattr(B, 'validate_candidate', _boom)
    with pytest.raises(Boom):
        run_build(tmp_path, ['alfa', 'beta', 'gamă', 'delta'], out=out, reg=reg)
    new = reg.read_text(encoding='utf-8')
    # The unused id stays (documented), the old lines are unchanged, and the next build reuses it.
    assert new.startswith(old) and new.endswith('4\tdelta\n')
    monkeypatch.undo()
    run_build(tmp_path, ['alfa', 'beta', 'gamă', 'delta'], out=out, reg=reg)
    assert ids(out)['delta'] == 4
    assert reg.read_text(encoding='utf-8') == new


def test_registry_mismatch_is_rejected(good, monkeypatch):
    """A word id that disagrees with the registry must never be published."""
    tmp_path, out, reg = good
    snap = (digest(out), listing(out.parent))
    real = B._apply_word_ids

    def corrupt(conn, *a, **k):
        n = real(conn, *a, **k)
        conn.execute("UPDATE words SET word_id = word_id + 1000 WHERE word = 'alfa'")
        return n
    monkeypatch.setattr(B, '_apply_word_ids', corrupt)
    with pytest.raises(B.BuildError, match='differ from the registry'):
        run_build(tmp_path, ['alfa', 'beta', 'gamă'], out=out, reg=reg)
    _assert_untouched(out, *snap)


def test_first_build_failure_creates_no_output(tmp_path, monkeypatch):
    monkeypatch.setattr(B, 'merge_synonyms', _boom)
    out = tmp_path / 'out' / 'ui.db'
    with pytest.raises(Boom):
        run_build(tmp_path, ['alfa'], out=out)
    assert not out.exists()
    assert listing(out.parent) == ['ui.db.lock']


def test_missing_shortlist_is_an_error(tmp_path):
    with pytest.raises(B.BuildError, match='Missing'):
        B.build(tmp_path / 'nope.csv', None, None, None, tmp_path / 'ui.db',
                inputs=inputs(tmp_path), registry_path=tmp_path / 'r.tsv')


# ---- empty / small builds, input policy ----------------------------------------------

def test_empty_build_is_rejected_even_with_low_minimum(good):
    tmp_path, out, reg = good
    snap = (digest(out), listing(out.parent))
    with pytest.raises(B.BuildError, match='no words'):
        run_build(tmp_path, [], out=out, reg=reg, min_words=0)
    _assert_untouched(out, *snap)


def test_small_build_needs_explicit_minimum(tmp_path):
    with pytest.raises(B.BuildError, match='below the minimum'):
        run_build(tmp_path, ['alfa'], min_words=B.MIN_WORDS_DEFAULT)
    assert not (tmp_path / 'out' / 'ui.db').exists()


def test_large_shrink_is_rejected_unless_allowed(tmp_path):
    out, reg = run_build(tmp_path, [f'w{i:03d}' for i in range(10)])
    snap = digest(out)
    with pytest.raises(B.BuildError, match='previous output'):
        run_build(tmp_path, ['w000'], out=out, reg=reg)
    assert digest(out) == snap
    run_build(tmp_path, ['w000'], out=out, reg=reg, allow_shrink=True)
    assert set(ids(out)) == {'w000'}


def test_missing_required_input_stops_a_production_build(tmp_path):
    with pytest.raises(B.BuildError, match='required inputs are missing'):
        run_build(tmp_path, ['alfa'], allow_missing_inputs=False)
    assert not (tmp_path / 'out' / 'ui.db').exists()


def test_input_policy_lists():
    assert set(B.Inputs.REQUIRED).isdisjoint(B.Inputs.OPTIONAL)
    assert set(B.Inputs.REQUIRED) | set(B.Inputs.OPTIONAL) == {
        f.name for f in B.dataclasses.fields(B.Inputs)}


# ---- stale sidecars -------------------------------------------------------------------

def test_stale_empty_sidecars_are_removed(good):
    tmp_path, out, reg = good
    out.with_name('ui.db-wal').write_bytes(b'')
    out.with_name('ui.db-shm').write_bytes(b'\0' * 32768)
    run_build(tmp_path, ['alfa', 'beta', 'gamă', 'delta'], out=out, reg=reg)
    assert listing(out.parent) == ['ui.db', 'ui.db.lock']
    assert len(ids(out)) == 4


def test_nonempty_stale_wal_blocks_the_replace(good):
    tmp_path, out, reg = good
    out.with_name('ui.db-wal').write_bytes(b'old committed frames')
    snap = digest(out)
    with pytest.raises(B.BuildError, match='not empty'):
        run_build(tmp_path, ['alfa', 'beta', 'gamă', 'delta'], out=out, reg=reg)
    assert digest(out) == snap
    assert out.with_name('ui.db-wal').read_bytes() == b'old committed frames'
    assert not [p for p in listing(out.parent) if '.build-' in p]
    run_build(tmp_path, ['alfa', 'beta', 'gamă', 'delta'], out=out, reg=reg,
              discard_stale_wal=True)
    assert listing(out.parent) == ['ui.db', 'ui.db.lock']
    c = sqlite3.connect(f'file:{out}?mode=ro', uri=True)
    assert c.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    c.close()


def test_orphan_temp_from_a_killed_build_is_cleaned(good):
    tmp_path, out, reg = good
    orphan = out.parent / 'ui.db.build-dead.tmp'
    orphan.write_bytes(b'partial')
    run_build(tmp_path, ['alfa', 'beta', 'gamă'], out=out, reg=reg)
    assert not orphan.exists()


# ---- concurrency ----------------------------------------------------------------------

def test_second_builder_is_refused_while_the_first_holds_the_lock(good):
    tmp_path, out, reg = good
    snap = (digest(out), listing(out.parent))
    reg_bytes = reg.read_bytes()
    with B._output_lock(out):
        with pytest.raises(B.BuildError, match='another build holds'):
            run_build(tmp_path, ['alfa', 'beta', 'gamă', 'delta'], out=out, reg=reg)
    assert digest(out) == snap[0] and reg.read_bytes() == reg_bytes


def test_registry_lock_blocks_a_builder_to_another_output(good):
    tmp_path, out, reg = good
    other = tmp_path / 'other' / 'ui.db'
    reg_bytes = reg.read_bytes()
    with word_ids.registry_lock(reg):
        with pytest.raises(word_ids.RegistryLocked):
            run_build(tmp_path, ['alfa', 'zeta'], out=other, reg=reg)
    assert reg.read_bytes() == reg_bytes
    assert not other.exists()


def _worker(args):
    tmp, words, out, reg = args
    try:
        _quiet_build(Path(tmp), words, Path(out), Path(reg))
        return 'ok'
    except (B.BuildError, word_ids.RegistryLocked):
        return 'locked'


def _quiet_build(tmp, words, out, reg):
    # Separate shortlist per worker so processes never write the same file.
    import os
    sl = shortlist(tmp, words, name=f'sl-{os.getpid()}.csv')
    B.build(sl, None, None, None, out, inputs=inputs(tmp), registry_path=reg,
            min_words=1, allow_missing_inputs=True)


def test_concurrent_builders_never_duplicate_ids(tmp_path):
    out = tmp_path / 'out' / 'ui.db'
    reg = tmp_path / 'reg' / 'word_ids.tsv'
    jobs = [(str(tmp_path), [f'a{i}{j}' for j in range(30)], str(out), str(reg))
            for i in range(4)]
    with multiprocessing.get_context('fork').Pool(4) as pool:
        results = pool.map(_worker, jobs)
    assert 'ok' in results
    registry = word_ids.load_registry(reg)
    assert len(set(registry.values())) == len(registry)       # no duplicate ids
    assert sorted(registry.values()) == list(range(1, len(registry) + 1))
    assert ids(out) == {w: registry[w] for w in ids(out)}
    assert [p for p in listing(out.parent) if p not in ('ui.db', 'ui.db.lock')] == []


def test_cli_refuses_a_small_default_build(tmp_path):
    """The CLI keeps the production minimum. Run in a scratch cwd so no repo file is read."""
    (tmp_path / 'data' / 'processed').mkdir(parents=True)
    (tmp_path / 'data' / 'processed' / 'forgotten_words_shortlist.csv').write_text(
        HEADER + 'alfa,0.5,absent,relevant,100,\n', encoding='utf-8')
    r = subprocess.run(
        [sys.executable, str(ROOT / 'tools' / 'build_ui_db.py'), '--out', str(tmp_path / 'o' / 'ui.db'),
         '--registry', str(tmp_path / 'reg.tsv'), '--allow-missing-inputs'],
        cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode != 0
    assert 'below the minimum' in r.stderr
    assert not (tmp_path / 'o' / 'ui.db').exists()
