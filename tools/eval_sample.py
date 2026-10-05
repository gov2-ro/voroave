#!/usr/bin/env python3
"""Deterministic stratified sample for the ranking evaluation (brief F09).

    python3 tools/eval_sample.py                       # writes data/eval/*
    python3 tools/eval_sample.py --ui-db PATH --out-dir DIR --n 1200 --seed STR
    python3 tools/eval_sample.py --provenance-out docs/eval/sample-provenance.json \
                                 --words-out docs/eval/sample-words.tsv

The protocol is docs/eval/protocol.md. This script is the "sampling" part of it.

Safety
  * It opens ui.db READ-ONLY (`mode=ro&immutable=1`). It never writes next to it.
  * It never opens private/app.db. Annotations and votes are out of scope.
  * It is deterministic: the same ui.db bytes, seed, n and script version give
    byte-identical outputs. Nothing depends on row order, time or the process.

Outputs (default directory data/eval/, gitignored)
  annotator_export.csv   what annotators see: item_id, word, definition, senses.
                         NO score, verdict, seam, flag, count or register column.
  sample_key.csv         analysis-only key: stratum, split, group, weight and every
                         baseline feature. Never give this file to an annotator.
Optional committed outputs
  --words-out            word list with item_id, split and stratum (no scores)
  --provenance-out       build identity, seed, strata counts, script version

Stdlib only.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_VERSION = "1.0.0"
DEFAULT_SEED = "f09-voroave-eval-v1"
DEFAULT_N = 1200
FLOOR_PER_CELL = 3
DEV_SHARE_PERCENT = 40            # 40% development, 60% held-out test, by lemma group
SCORE_EDGES = (60, 80, 92, 105)   # band edges; 92 is RELEVANT_MIN_SCORE
SCORE_BAND_NAMES = ("lt60", "60-79", "80-91", "92-104", "ge105")

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_UI_DB = ROOT / "public" / "data" / "ui.db"
DEFAULT_OUT = ROOT / "data" / "eval"

# The ONLY columns an annotator may receive.
ANNOTATOR_COLUMNS = ["item_id", "word", "definition", "senses"]

# Columns of the analysis key. Baseline features come from ui.db as they are.
FEATURE_COLUMNS = [
    "quality_score", "modern_occ", "modern_ppm", "dex_frequency", "zipf_frequency",
    "hist_occ", "hist_docs", "dict_count", "family_ratio", "newest_dict_year",
    "in_current_dict", "has_definition", "modern_band", "dex_register",
]
KEY_COLUMNS = (
    ["item_id", "word", "split", "group_id", "stratum", "seam", "verdict",
     "score_band", "attr", "def_kind", "cell_size", "cell_quota", "weight"]
    + FEATURE_COLUMNS
)

DIMINUTIVE_RE = re.compile(r"^\s*Diminutiv al lui\s+([^\s.|,;]+)")


def h(*parts: str) -> int:
    """Stable 64-bit integer hash of the joined parts."""
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def score_band(score) -> str:
    s = score if score is not None else 0
    for edge, name in zip(SCORE_EDGES, SCORE_BAND_NAMES):
        if s < edge:
            return name
    return SCORE_BAND_NAMES[-1]


def attr_of(row: dict) -> str:
    """One attribute per word. Precedence: variant, regional, derived, plain."""
    if row.get("variant_like") or row.get("archaic_spelling") or row.get("dex_variant"):
        return "variant"
    if row.get("regional_only"):
        return "regional"
    if row.get("deverbal_like") or row.get("diminutive_like"):
        return "derived"
    return "plain"


# ---------------------------------------------------------------- allocation

def allocate(sizes: dict, n: int, floor: int) -> dict:
    """Square-root-proportional allocation with a per-cell floor.

    Every non-empty cell gets min(size, floor). The rest goes in proportion to
    sqrt(size), capped at the cell size, by largest remainder. Ties break by key.
    """
    quota = {k: min(s, floor) for k, s in sizes.items()}
    total = sum(sizes.values())
    n = min(n, total)
    remaining = n - sum(quota.values())
    while remaining > 0:
        open_cells = [k for k in sizes if quota[k] < sizes[k]]
        if not open_cells:
            break
        weight = {k: math.sqrt(sizes[k]) for k in open_cells}
        wsum = sum(weight.values())
        share = {k: remaining * weight[k] / wsum for k in open_cells}
        add = {k: min(int(share[k]), sizes[k] - quota[k]) for k in open_cells}
        given = sum(add.values())
        if given == 0:
            # Largest remainder, one unit at a time.
            order = sorted(open_cells, key=lambda k: (-(share[k] - int(share[k])), k))
            for k in order[:remaining]:
                quota[k] += 1
            break
        for k, v in add.items():
            quota[k] += v
        remaining -= given
    return quota


# ---------------------------------------------------------------- grouping

class UnionFind:
    def __init__(self):
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            # The smaller string is the root, so the group id is order-independent.
            lo, hi = (ra, rb) if ra < rb else (rb, ra)
            self.parent[hi] = lo


def build_groups(rows: list[dict], inflected_db: Path | None) -> dict[str, str]:
    """Map each word to a group id (its smallest member or target string).

    Links: variant_of, spelling_of, dex_variant_of, deverbal_of, the target of
    "Diminutiv al lui X", and (optional) words that are forms of one lexeme in
    inflected_forms.db. Targets need not be in the table: two words sharing a
    target form one group.
    """
    uf = UnionFind()
    words = {r["word"] for r in rows}
    for r in rows:
        w = r["word"]
        uf.find(w)
        for col in ("variant_of", "spelling_of", "dex_variant_of", "deverbal_of"):
            t = (r.get(col) or "").strip()
            if t and t != w:
                uf.union(w, t)
        m = DIMINUTIVE_RE.match(r.get("definition") or "")
        if m and r.get("diminutive_like"):
            uf.union(w, m.group(1).lower())
    if inflected_db is not None:
        conn = sqlite3.connect(f"file:{inflected_db}?mode=ro&immutable=1", uri=True)
        try:
            by_lexeme: dict[int, list[str]] = defaultdict(list)
            sorted_words = sorted(words)
            for i in range(0, len(sorted_words), 500):
                chunk = sorted_words[i:i + 500]
                marks = ",".join("?" * len(chunk))
                for form, lid in conn.execute(
                        f"SELECT form, lexeme_id FROM inflected WHERE form IN ({marks})", chunk):
                    by_lexeme[lid].append(form)
            for forms in by_lexeme.values():
                for f in forms[1:]:
                    uf.union(forms[0], f)
        finally:
            conn.close()
    return {w: uf.find(w) for w in words}


def split_of(group_id: str, seed: str) -> str:
    return "dev" if h(seed, "split", group_id) % 100 < DEV_SHARE_PERCENT else "test"


# ---------------------------------------------------------------- loading

def open_ro(path: Path) -> sqlite3.Connection:
    # immutable=1 stops SQLite creating -shm/-wal files beside a WAL-mode file.
    conn = sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def load_rows(conn: sqlite3.Connection) -> list[dict]:
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(words)")}
    want = ["word", "definition", "seam", "verdict", "regional_only", "variant_like",
            "archaic_spelling", "dex_variant", "deverbal_like", "diminutive_like",
            "variant_of", "spelling_of", "dex_variant_of", "deverbal_of"] + FEATURE_COLUMNS
    missing = [c for c in ("word", "seam", "verdict", "quality_score") if c not in cols]
    if missing:
        raise SystemExit(f"ui.db words table lacks columns: {missing}")
    sel = ", ".join(c if c in cols else f"NULL AS {c}" for c in dict.fromkeys(want))
    rows = [dict(r) for r in conn.execute(f"SELECT {sel} FROM words ORDER BY word")]
    structured: set[str] = set()
    try:
        structured = {r[0] for r in conn.execute("SELECT DISTINCT word FROM senses")}
    except sqlite3.Error:
        pass
    for r in rows:
        r["def_kind"] = "structured" if r["word"] in structured else "flat"
    return rows


def load_senses(conn: sqlite3.Connection, words: set[str]) -> dict[str, str]:
    """Plain numbered sense text for annotators. No tags: they carry register labels."""
    out: dict[str, list[str]] = defaultdict(list)
    try:
        for r in conn.execute(
                "SELECT word, breadcrumb, text FROM senses WHERE kind = 'sense' "
                "AND text IS NOT NULL AND text != '' ORDER BY word, ord"):
            if r["word"] in words:
                out[r["word"]].append(f"{r['breadcrumb']} {r['text']}".strip())
    except sqlite3.Error:
        pass
    return {w: " | ".join(v) for w, v in out.items()}


# ---------------------------------------------------------------- sampling

def draw(rows: list[dict], groups: dict[str, str], n: int, seed: str) -> list[dict]:
    cells: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        r["score_band"] = score_band(r.get("quality_score"))
        r["attr"] = attr_of(r)
        cells[(r["seam"], r["verdict"], r["score_band"], r["attr"])].append(r)
    sizes = {k: len(v) for k, v in cells.items()}
    quota = allocate(sizes, n, FLOOR_PER_CELL)
    picked: list[dict] = []
    for key in sorted(cells):
        members = sorted(cells[key], key=lambda r: (h(seed, "draw", r["word"]), r["word"]))
        by_kind = {"structured": [], "flat": []}
        for r in members:
            by_kind[r["def_kind"]].append(r)
        # Alternate structured / flat so both definition kinds appear in every cell.
        order, i = [], 0
        queues = [by_kind["structured"], by_kind["flat"]]
        while len(order) < quota[key] and (queues[0] or queues[1]):
            q = queues[i % 2] or queues[(i + 1) % 2]
            order.append(q.pop(0))
            i += 1
        for r in order:
            r["stratum"] = "|".join(key)
            r["cell_size"] = sizes[key]
            r["cell_quota"] = quota[key]
            r["weight"] = round(sizes[key] / quota[key], 6)
            r["group_id"] = groups[r["word"]]
            r["split"] = split_of(r["group_id"], seed)
            picked.append(r)
    for r in picked:
        r["item_id"] = "E" + hashlib.sha256(f"{seed}\x1fid\x1f{r['word']}".encode()).hexdigest()[:8]
    ids = [r["item_id"] for r in picked]
    if len(set(ids)) != len(ids):
        raise SystemExit("item_id collision; change the seed")
    return picked


# ---------------------------------------------------------------- output

def write_csv(path: Path, columns: list[str], records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for r in records:
            w.writerow({c: ("" if r.get(c) is None else r.get(c)) for c in columns})


def sha256_file(path: Path) -> str:
    d = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            d.update(chunk)
    return d.hexdigest()


def summarize(picked: list[dict]) -> dict:
    def count(fn):
        c: dict[str, int] = defaultdict(int)
        for r in picked:
            c[fn(r)] += 1
        return dict(sorted(c.items()))
    return {
        "n": len(picked),
        "by_seam": count(lambda r: r["seam"]),
        "by_verdict": count(lambda r: r["verdict"]),
        "by_score_band": count(lambda r: r["score_band"]),
        "by_attr": count(lambda r: r["attr"]),
        "by_def_kind": count(lambda r: r["def_kind"]),
        "by_split": count(lambda r: r["split"]),
        "by_seam_verdict": count(lambda r: f"{r['seam']}|{r['verdict']}"),
        "n_cells": len({r["stratum"] for r in picked}),
        "n_groups": len({r["group_id"] for r in picked}),
    }


def run(ui_db: Path, out_dir: Path, n: int, seed: str, inflected_db: Path | None,
        provenance_out: Path | None, words_out: Path | None) -> dict:
    conn = open_ro(ui_db)
    try:
        rows = load_rows(conn)
        groups = build_groups(rows, inflected_db)
        picked = draw(rows, groups, n, seed)
        senses = load_senses(conn, {r["word"] for r in picked})
    finally:
        conn.close()
    # Annotator order is a hash shuffle, so row order carries no stratum or score.
    picked.sort(key=lambda r: (h(seed, "order", r["word"]), r["word"]))
    for r in picked:
        r["senses"] = senses.get(r["word"], "")
    write_csv(out_dir / "annotator_export.csv", ANNOTATOR_COLUMNS, picked)
    keyed = sorted(picked, key=lambda r: r["word"])
    write_csv(out_dir / "sample_key.csv", KEY_COLUMNS, keyed)
    summary = summarize(picked)
    if words_out is not None:
        words_out.parent.mkdir(parents=True, exist_ok=True)
        lines = ["item_id\tword\tsplit\tstratum"]
        lines += [f"{r['item_id']}\t{r['word']}\t{r['split']}\t{r['stratum']}" for r in keyed]
        words_out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if provenance_out is not None:
        st = ui_db.stat()
        prov = {
            "script": "tools/eval_sample.py",
            "script_version": SCRIPT_VERSION,
            "seed": seed,
            "n_requested": n,
            "floor_per_cell": FLOOR_PER_CELL,
            "dev_share_percent": DEV_SHARE_PERCENT,
            "score_band_edges": list(SCORE_EDGES),
            "inflection_families_used": inflected_db is not None,
            "inflected_db": ({"size_bytes": inflected_db.stat().st_size,
                              "sha256": sha256_file(inflected_db)}
                             if inflected_db is not None else None),
            "ui_db": {
                "path": "public/data/ui.db",
                "size_bytes": st.st_size,
                "sha256": sha256_file(ui_db),
                "mtime_utc": datetime.fromtimestamp(st.st_mtime, timezone.utc)
                                     .strftime("%Y-%m-%dT%H:%M:%SZ"),
                "build_date_note": "ui.db stores no build date; mtime is a proxy",
                "words_rows": len(rows),
            },
            "strata": summary,
            "sha256_annotator_export": sha256_file(out_dir / "annotator_export.csv"),
            "sha256_sample_key": sha256_file(out_dir / "sample_key.csv"),
        }
        provenance_out.parent.mkdir(parents=True, exist_ok=True)
        provenance_out.write_text(json.dumps(prov, indent=2, ensure_ascii=False, sort_keys=True)
                                  + "\n", encoding="utf-8")
    return summary


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--ui-db", type=Path, default=DEFAULT_UI_DB)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--n", type=int, default=DEFAULT_N)
    ap.add_argument("--seed", default=DEFAULT_SEED)
    ap.add_argument("--inflected-db", type=Path, default=None,
                    help="data/processed/inflected_forms.db; adds shared-lexeme links to groups")
    ap.add_argument("--provenance-out", type=Path, default=None)
    ap.add_argument("--words-out", type=Path, default=None)
    a = ap.parse_args(argv)
    if not a.ui_db.exists():
        print(f"missing {a.ui_db}", file=sys.stderr)
        return 1
    summary = run(a.ui_db, a.out_dir, a.n, a.seed, a.inflected_db, a.provenance_out, a.words_out)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
