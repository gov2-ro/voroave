"""Guards for tools/eval_sample.py (F09): determinism and annotator-export exclusion.

Uses a tiny synthetic ui.db in a temp dir. It never opens the real ui.db or app.db.
"""
import csv
import random
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
import eval_sample as ev  # noqa: E402

FORBIDDEN = {"quality_score", "verdict", "seam", "regional_only", "variant_like",
             "archaic_spelling", "dex_variant", "modern_occ", "hist_occ", "dex_frequency",
             "dex_register", "in_current_dict", "modern_band", "split", "stratum", "weight"}


def make_db(path: Path, order_seed: int = 0) -> None:
    conn = sqlite3.connect(path)
    conn.execute("""CREATE TABLE words (word TEXT PRIMARY KEY, definition TEXT, seam TEXT,
        verdict TEXT, quality_score INTEGER, regional_only INTEGER, variant_like INTEGER,
        archaic_spelling INTEGER, dex_variant INTEGER, deverbal_like INTEGER,
        diminutive_like INTEGER, variant_of TEXT, spelling_of TEXT, dex_variant_of TEXT,
        deverbal_of TEXT, modern_occ INTEGER, dex_frequency REAL, dex_register TEXT)""")
    conn.execute("CREATE TABLE senses (word TEXT, ord INTEGER, breadcrumb TEXT, depth INTEGER,"
                 " kind TEXT, text TEXT, tags TEXT, synonyms TEXT)")
    rows = []
    for i in range(120):
        w = f"cuvant{i:03d}"
        rows.append((w, f"Definitie {i}.", "relevant" if i % 3 == 0 else "curiosity",
                     ["extinct", "declining", "historical_only", "absent"][i % 4],
                     40 + (i * 7) % 80, int(i % 10 == 0), int(i % 11 == 0), 0, 0, 0,
                     int(i % 13 == 0), None, None, None, None, i, 0.5, "invechit|regional"))
    # A diminutive pair and a variant pair that must share a group.
    rows.append(("pauas", "Diminutiv al lui paun .", "curiosity", "declining", 70,
                 0, 0, 0, 0, 0, 1, None, None, None, None, 3, 0.5, ""))
    rows.append(("paunel", "Diminutiv al lui paun .", "curiosity", "declining", 70,
                 0, 0, 0, 0, 0, 1, None, None, None, None, 3, 0.5, ""))
    random.Random(order_seed).shuffle(rows)
    conn.executemany("INSERT INTO words VALUES (" + ",".join("?" * 18) + ")", rows)
    for i in range(0, 120, 2):
        conn.execute("INSERT INTO senses VALUES (?,1,'1.',0,'sense',?,'invechit',NULL)",
                     (f"cuvant{i:03d}", f"Sens {i}."))
    conn.commit()
    conn.close()


def read(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.reader(f))


def test_deterministic_and_row_order_independent(tmp_path):
    a, b = tmp_path / "a.db", tmp_path / "b.db"
    make_db(a, 1)
    make_db(b, 2)   # same rows, different insertion order
    ev.run(a, tmp_path / "o1", 40, "s", None, None, None)
    ev.run(a, tmp_path / "o2", 40, "s", None, None, None)
    ev.run(b, tmp_path / "o3", 40, "s", None, None, None)
    for name in ("annotator_export.csv", "sample_key.csv"):
        base = (tmp_path / "o1" / name).read_bytes()
        assert base == (tmp_path / "o2" / name).read_bytes()
        assert base == (tmp_path / "o3" / name).read_bytes()
    ev.run(a, tmp_path / "o4", 40, "other-seed", None, None, None)
    assert (tmp_path / "o4" / "sample_key.csv").read_bytes() != (tmp_path / "o1" / "sample_key.csv").read_bytes()


def test_annotator_export_has_only_whitelisted_columns(tmp_path):
    db = tmp_path / "u.db"
    make_db(db)
    ev.run(db, tmp_path / "o", 40, "s", None, None, None)
    rows = read(tmp_path / "o" / "annotator_export.csv")
    assert rows[0] == ev.ANNOTATOR_COLUMNS
    assert not (set(rows[0]) & FORBIDDEN)
    text = (tmp_path / "o" / "annotator_export.csv").read_text(encoding="utf-8")
    assert "invechit" not in text          # register tags and sense tags never leak
    key = read(tmp_path / "o" / "sample_key.csv")
    assert {"seam", "verdict", "split", "weight"} <= set(key[0])


def test_related_words_share_a_group_and_split(tmp_path):
    db = tmp_path / "u.db"
    make_db(db)
    conn = ev.open_ro(db)
    groups = ev.build_groups(ev.load_rows(conn), None)
    conn.close()
    assert groups["pauas"] == groups["paunel"]
    assert ev.split_of(groups["pauas"], "s") == ev.split_of(groups["paunel"], "s")


def test_allocation_floor_and_total():
    q = ev.allocate({"a": 1000, "b": 10, "c": 2}, 60, 3)
    assert q["c"] == 2 and q["b"] >= 3 and sum(q.values()) == 60
    assert all(q[k] <= s for k, s in {"a": 1000, "b": 10, "c": 2}.items())


def test_read_only_open_does_not_modify_db(tmp_path):
    db = tmp_path / "u.db"
    make_db(db)
    before = db.read_bytes()
    ev.run(db, tmp_path / "o", 40, "s", None, None, None)
    assert db.read_bytes() == before
