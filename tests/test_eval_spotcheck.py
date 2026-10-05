"""Guards for the Stage 0 spot-check (tools/eval_sample.py --spotcheck, tools/eval_spotcheck.py).

Synthetic ui.db and synthetic marks only. No real ui.db, no app.db.
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
sys.path.insert(0, str(Path(__file__).parent))
import eval_sample as ev  # noqa: E402
import eval_spotcheck as sc  # noqa: E402
from test_eval_sample import make_db, FORBIDDEN  # noqa: E402


def rows(path, delim="\t"):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter=delim))


def test_spotcheck_is_deterministic_and_covers_bands(tmp_path):
    a, b = tmp_path / "a.db", tmp_path / "b.db"
    make_db(a, 1)
    make_db(b, 2)
    ev.run_spotcheck(a, tmp_path / "o1", 40, ev.SPOT_SEED)
    ev.run_spotcheck(b, tmp_path / "o2", 40, ev.SPOT_SEED)
    for name in ("spotcheck_marks.tsv", "spotcheck_key.csv"):
        assert (tmp_path / "o1" / name).read_bytes() == (tmp_path / "o2" / name).read_bytes()
    ev.run_spotcheck(a, tmp_path / "o3", 40, "other")
    assert (tmp_path / "o3" / "spotcheck_key.csv").read_bytes() != (tmp_path / "o1" / "spotcheck_key.csv").read_bytes()
    key = rows(tmp_path / "o1" / "spotcheck_key.csv", ",")
    assert len(key) == 40
    assert {r["score_band"] for r in key} == set(ev.SCORE_BAND_NAMES)


def test_blind_export_columns(tmp_path):
    db = tmp_path / "u.db"
    make_db(db)
    ev.run_spotcheck(db, tmp_path / "o", 30, ev.SPOT_SEED)
    text = (tmp_path / "o" / "spotcheck_marks.tsv").read_text(encoding="utf-8")
    header = text.splitlines()[0].split("\t")
    assert header == ["item_id", "word", "definition", "mark"]
    assert not (set(header) & FORBIDDEN)
    assert "invechit" not in text
    assert all(r["mark"] == "" for r in rows(tmp_path / "o" / "spotcheck_marks.tsv"))


def test_auc_on_constructed_case():
    def it(mark, score):
        return {"mark": mark, "score": score, "modern_occ": 0, "dex_frequency": 0}
    items = [it("bun", 9), it("bun", 7), it("slab", 8), it("slab", 1)]
    # bun>slab pairs: 9>8, 9>1, 7>1 win; 7<8 loses -> 3/4
    assert sc.auc(items, lambda i: i["score"]) == 0.75
    assert sc.auc(items, lambda i: 0) == 0.5          # all ties
    assert sc.auc([it("bun", 1)], lambda i: i["score"]) is None


def test_parse_mark_handles_question_and_blank():
    assert sc.parse_mark("bun") == ("bun", False)
    assert sc.parse_mark(" Slab? ") == ("slab", True)
    assert sc.parse_mark("?") == (None, True)
    assert sc.parse_mark("") == (None, False)
    try:
        sc.parse_mark("great")
        assert False
    except ValueError:
        pass


def test_report_end_to_end_with_missing_and_bad_marks(tmp_path):
    db = tmp_path / "u.db"
    make_db(db)
    d = tmp_path / "o"
    ev.run_spotcheck(db, d, 30, ev.SPOT_SEED)
    key = {r["item_id"]: r for r in rows(d / "spotcheck_key.csv", ",")}
    sheet = rows(d / "spotcheck_marks.tsv")
    for i, r in enumerate(sheet):
        # Mark by score: high score bun, low score slab, a few left blank or "?".
        s = float(key[r["item_id"]]["score"])
        r["mark"] = "bun" if s >= 90 else ("slab" if s < 60 else "meh")
        if i == 0:
            r["mark"] = ""
        if i == 1:
            r["mark"] = "?"
        if i == 2:
            r["mark"] = "oops"
    with open(d / "spotcheck_marks.tsv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=sc_cols(), delimiter="\t", lineterminator="\n")
        w.writeheader()
        w.writerows(sheet)
    items, bad = sc.load(d / "spotcheck_marks.tsv", d / "spotcheck_key.csv")
    assert len(bad) == 1 and "oops" in bad[0]
    assert len(items) == 29
    text = sc.report(items, bad)
    assert "rough signal" in text
    assert "Missing or '?' only: 2" in text
    assert "current score" in text


def sc_cols():
    return ev.SPOT_MARKS_COLUMNS


def test_report_with_no_marks(tmp_path):
    db = tmp_path / "u.db"
    make_db(db)
    ev.run_spotcheck(db, tmp_path / "o", 20, ev.SPOT_SEED)
    items, bad = sc.load(tmp_path / "o" / "spotcheck_marks.tsv", tmp_path / "o" / "spotcheck_key.csv")
    assert "No marks yet" in sc.report(items, bad)
