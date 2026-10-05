#!/usr/bin/env python3
"""Stage 0 curator spot-check: read the owner's marks and print a one-page result.

    python3 tools/eval_sample.py --spotcheck --n 150      # makes the blind sheet + key
    # The owner fills the `mark` column of data/eval/spotcheck_marks.tsv.
    python3 tools/eval_spotcheck.py                        # prints the result

Marks: bun (good find), meh, slab (dud). A "?" after a mark ("bun?") means unsure.
A lone "?" or a blank cell means no judgment; the word is left out.

Marks can also come from the web UI, as custom tags on each word:
sc-bun, sc-meh, sc-slab. Add -q for unsure: sc-bun-q, sc-meh-q, sc-slab-q.

    python3 tools/eval_spotcheck.py --from-appdb                  # reads private/app.db, read-only
    python3 tools/eval_spotcheck.py --from-appdb --user 3 --user 7
    python3 tools/eval_spotcheck.py --from-tsv-export FILE        # FILE from api/_export_spotcheck.php

Rules for the tags of one user on one word: tags of two different marks make a conflict;
the word is left out and the conflict is listed. Any -q tag makes the mark unsure (kept).
With two or more markers the report adds percent agreement and Cohen's kappa.

The TSV path reads two local files only. The app.db path opens app.db read-only
(sqlite mode=ro) and never writes. It never opens ui.db. Stdlib only.
Docs: docs/eval/protocol.md, "Stage 0".
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DIR = ROOT / "data" / "eval"
VALID = {"bun", "meh", "slab"}
BAND_ORDER = ("ge105", "92-104", "80-91", "60-79", "lt60")
BOOT_REPS = 2000
BOOT_SEED = 20261005


def parse_mark(raw):
    """Return (mark or None, unsure). Raise ValueError for an unknown mark."""
    t = (raw or "").strip().lower()
    unsure = "?" in t
    t = t.replace("?", "").strip()
    if not t:
        return None, unsure
    if t not in VALID:
        raise ValueError(raw)
    return t, unsure


def _num(x):
    return float(x) if x not in ("", None) else 0.0


def item_from_key(k, mark, unsure):
    return {
        "word": k["word"], "mark": mark, "unsure": unsure,
        "rank": int(k["rank"]), "n_total": int(k["n_total"]),
        "score": _num(k["score"]), "band": k["score_band"], "seam": k["seam"],
        "modern_occ": _num(k["modern_occ"]), "dex_frequency": _num(k["dex_frequency"]),
    }


def load_key(key_path: Path):
    with open(key_path, newline="", encoding="utf-8") as f:
        return {r["item_id"]: r for r in csv.DictReader(f)}


def load(marks_path: Path, key_path: Path):
    key = load_key(key_path)
    items, bad = [], []
    with open(marks_path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            k = key.get(r["item_id"])
            if k is None:
                bad.append(f"{r['item_id']}: not in key")
                continue
            try:
                mark, unsure = parse_mark(r.get("mark"))
            except ValueError:
                bad.append(f"{r['word']}: unknown mark {r.get('mark')!r}")
                continue
            items.append(item_from_key(k, mark, unsure))
    return items, bad


# ---- Marks typed as tags in the web UI -------------------------------------------------
TAG_RE = re.compile(r"^sc-(bun|meh|slab)(-q)?$")


def parse_sc_tag(tag):
    """'sc-bun-q' -> ('bun', True). None when the tag is not a spot-check mark."""
    m = TAG_RE.match((tag or "").strip().lower())
    return (m.group(1), bool(m.group(2))) if m else None


def resolve_tags(tags):
    """Rule for the sc- tags one user put on one word.
    Returns (mark, unsure, conflict). Two different marks = conflict, no mark.
    Any -q tag makes the mark unsure. Tags that are not sc- marks are ignored."""
    parsed = [p for p in map(parse_sc_tag, tags) if p]
    if not parsed:
        return None, False, False
    marks = {m for m, _ in parsed}
    if len(marks) > 1:
        return None, False, True
    return marks.pop(), any(u for _, u in parsed), False


def collect_marks(rows):
    """rows: iterable of (user_id, word, tag). Returns {user: {word: [tags]}}."""
    out = defaultdict(lambda: defaultdict(list))
    for uid, word, tag in rows:
        if parse_sc_tag(tag):
            out[int(uid)][word].append(tag)
    return out


def read_appdb(path: Path):
    """Read live sc- tags from app.db, read-only. mode=ro (not immutable), so the WAL is honoured."""
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        rows = conn.execute("SELECT user_id, word, tags FROM annotations "
                            "WHERE deleted = 0 AND tags LIKE '%sc-%'").fetchall()
    finally:
        conn.close()
    flat = []
    for uid, word, tags in rows:
        try:
            lst = json.loads(tags or "[]")
        except ValueError:
            continue
        flat += [(uid, word, t) for t in lst if isinstance(t, str)]
    return collect_marks(flat)


def read_tsv_export(path: Path):
    with open(path, newline="", encoding="utf-8") as f:
        lines = [ln.rstrip("\n").split("\t") for ln in f if ln.strip()]
    if not lines or lines[0] != ["user_id", "word", "tag"]:
        raise SystemExit(f"{path}: expected the header user_id<TAB>word<TAB>tag")
    flat = []
    for ln in lines[1:]:
        if len(ln) != 3 or not ln[0].isdigit():
            raise SystemExit(f"{path}: bad row {ln!r}")
        flat.append((int(ln[0]), ln[1], ln[2]))
    return collect_marks(flat)


def items_for_user(by_word, key):
    """Join one user's tags with the key (by word). Returns (items, notes, marks)
    where marks is {word: mark} for words judged."""
    by_key_word = {k["word"]: k for k in key.values()}
    items, notes, marks = [], [], {}
    for word, tags in sorted(by_word.items()):
        k = by_key_word.get(word)
        if k is None:
            notes.append(f"{word}: not in the sample, ignored")
            continue
        mark, unsure, conflict = resolve_tags(tags)
        if conflict:
            notes.append(f"{word}: conflicting tags {sorted(tags)}, left out")
            continue
        items.append(item_from_key(k, mark, unsure))
        marks[word] = mark
    return items, notes, marks


def cohen_kappa(pairs):
    """pairs: list of (a, b) labels. Returns None when undefined (no pairs, or chance agreement = 1)."""
    n = len(pairs)
    if n == 0:
        return None
    po = sum(a == b for a, b in pairs) / n
    cats = {x for p in pairs for x in p}
    pe = sum((sum(a == c for a, _ in pairs) / n) * (sum(b == c for _, b in pairs) / n) for c in cats)
    return None if pe == 1 else (po - pe) / (1 - pe)


def agreement_lines(user_marks):
    """user_marks: {user: {word: mark}}. One line per pair of markers."""
    out = []
    users = sorted(user_marks)
    for i, a in enumerate(users):
        for b in users[i + 1:]:
            common = sorted(set(user_marks[a]) & set(user_marks[b]))
            pairs = [(user_marks[a][w], user_marks[b][w]) for w in common]
            if not pairs:
                out.append(f"  user {a} and user {b}: no words judged by both")
                continue
            agree = sum(x == y for x, y in pairs)
            kap = cohen_kappa(pairs)
            kt = "n/a" if kap is None else f"{kap:.2f}"
            out.append(f"  user {a} and user {b}: {len(pairs)} words in common, "
                       f"agree {agree} ({100 * agree / len(pairs):.0f}%), Cohen's kappa {kt}")
    return out


# Each ordering gives a number where HIGHER means "predicted better find".
ORDERINGS = {
    "current score": lambda i: i["score"],
    "modern count, low first": lambda i: -i["modern_occ"],
    "DEX prominence, high first": lambda i: i["dex_frequency"],
}


def auc(items, fn):
    """Chance that a random bun outranks a random slab. Ties count half. None if undefined."""
    bun = [fn(i) for i in items if i["mark"] == "bun"]
    slab = [fn(i) for i in items if i["mark"] == "slab"]
    if not bun or not slab:
        return None
    wins = sum((b > s) + 0.5 * (b == s) for b in bun for s in slab)
    return wins / (len(bun) * len(slab))


def boot_ci(items, stat, reps=BOOT_REPS, seed=BOOT_SEED):
    rng = random.Random(seed)
    vals = []
    for _ in range(reps):
        sample = [items[rng.randrange(len(items))] for _ in items]
        v = stat(sample)
        if v is not None:
            vals.append(v)
    if len(vals) < reps // 2:
        return None
    vals.sort()
    return vals[int(0.025 * len(vals))], vals[min(len(vals) - 1, int(0.975 * len(vals)))]


def tercile(i):
    f = (i["rank"] - 1) / i["n_total"]
    return "top" if f < 1 / 3 else ("middle" if f < 2 / 3 else "bottom")


def share_line(label, group):
    n = len(group)
    c = {m: sum(1 for i in group if i["mark"] == m) for m in VALID}
    if n == 0:
        return f"  {label:<10} no judged words"
    return (f"  {label:<10} n={n:<3} bun {c['bun']:>3} ({100 * c['bun'] / n:3.0f}%)  "
            f"meh {c['meh']:>3}  slab {c['slab']:>3} ({100 * c['slab'] / n:3.0f}%)")


def report(items, bad) -> str:
    out = []
    out.append("CURATOR SPOT-CHECK (Stage 0)")
    out.append("This is a rough signal. About 150 words is small. It can show a clear")
    out.append("pattern. It cannot settle a close call. It does not authorize a score change.")
    out.append("")
    judged = [i for i in items if i["mark"]]
    skipped = len(items) - len(judged)
    unsure = sum(1 for i in judged if i["unsure"])
    out.append(f"Words in sheet: {len(items)}. Judged: {len(judged)}. "
               f"Missing or '?' only: {skipped}. Marked unsure (kept): {unsure}.")
    for b in bad:
        out.append(f"  WARNING, row skipped: {b}")
    if not judged:
        out.append("No marks yet. Fill the `mark` column and run again.")
        return "\n".join(out)
    out.append("")
    out.append("1. Share of each mark, by place in the current ranking (thirds of the whole list)")
    for t in ("top", "middle", "bottom"):
        out.append(share_line(t, [i for i in judged if tercile(i) == t]))
    out.append("   By score band:")
    for b in BAND_ORDER:
        g = [i for i in judged if i["band"] == b]
        if g:
            out.append(share_line(b, g))
    out.append("   By seam:")
    for s in ("relevant", "curiosity"):
        out.append(share_line(s, [i for i in judged if i["seam"] == s]))
    out.append("")
    nb = sum(1 for i in judged if i["mark"] == "bun")
    ns = sum(1 for i in judged if i["mark"] == "slab")
    out.append("2. Does the order put good finds higher than duds?")
    out.append("   Number: the chance that a random bun ranks above a random slab.")
    out.append("   50% is a coin flip. 100% is a perfect order. meh words are left out here.")
    out.append(f"   Uses {nb} bun and {ns} slab words. Interval: rough 95% bootstrap.")
    if nb == 0 or ns == 0:
        out.append("   Cannot compute: it needs at least one bun and one slab.")
    else:
        for name, fn in ORDERINGS.items():
            a = auc(judged, fn)
            ci = boot_ci(judged, lambda s, fn=fn: auc(s, fn))
            rng = f"{100 * ci[0]:.0f}%-{100 * ci[1]:.0f}%" if ci else "n/a"
            out.append(f"   {name:<28} {100 * a:5.1f}%   interval {rng}")
        cur = ORDERINGS["current score"]
        for name, fn in list(ORDERINGS.items())[1:]:
            def diff(s, fn=fn):
                x, y = auc(s, cur), auc(s, fn)
                return None if x is None or y is None else x - y
            d = diff(judged)
            ci = boot_ci(judged, diff)
            rng = f"{100 * ci[0]:+.0f} to {100 * ci[1]:+.0f} points" if ci else "n/a"
            verdict = ("interval excludes zero" if ci and (ci[0] > 0 or ci[1] < 0)
                       else "interval includes zero: no clear difference")
            out.append(f"   current minus {name}: {100 * d:+.1f} points, {rng} ({verdict})")
    out.append("")
    out.append("3. Buried finds: bun words in the bottom third of the ranking")
    buried = sorted((i for i in judged if i["mark"] == "bun" and tercile(i) == "bottom"),
                    key=lambda i: i["rank"])
    out += [f"   rank {i['rank']:>6} of {i['n_total']}  score {i['score']:g}  {i['word']}"
            for i in buried] or ["   none"]
    out.append("")
    out.append("4. High duds: slab words in the top third of the ranking")
    high = sorted((i for i in judged if i["mark"] == "slab" and tercile(i) == "top"),
                  key=lambda i: i["rank"])
    out += [f"   rank {i['rank']:>6} of {i['n_total']}  score {i['score']:g}  {i['word']}"
            for i in high] or ["   none"]
    out.append("")
    out.append("Note: the sample is stratified by seam and score band, and the pooled numbers")
    out.append("in section 2 are not re-weighted. Read the per-band shares in section 1 first.")
    return "\n".join(out)


def tagged_report(by_user, key, users):
    """Report from tags. One section per marker, then agreement when there are two or more."""
    if users:
        missing = [u for u in users if u not in by_user]
        for u in missing:
            print(f"WARNING: user {u} has no sc- tags")
        by_user = {u: v for u, v in by_user.items() if u in users}
    if not by_user:
        return "No sc- tags found. Tag words in the web UI: sc-bun, sc-meh, sc-slab."
    out = [f"Markers found: {', '.join(str(u) for u in sorted(by_user))}"
           + ("" if users else " (all users holding an sc- tag)"), ""]
    user_marks = {}
    for u in sorted(by_user):
        items, notes, marks = items_for_user(by_user[u], key)
        user_marks[u] = {w: m for w, m in marks.items() if m}
        out.append(f"===== Marker: user {u} =====")
        out.append(report(items, notes))
        out.append("")
    if len(user_marks) >= 2:
        out.append("===== Agreement between markers =====")
        out.append("Words judged by both markers only. Unsure marks count as their mark.")
        out += agreement_lines(user_marks)
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    ap.add_argument("--marks", type=Path, default=None)
    ap.add_argument("--key", type=Path, default=None)
    ap.add_argument("--from-appdb", action="store_true",
                    help="read sc-* tags from app.db (read-only) instead of the marks TSV")
    ap.add_argument("--appdb", type=Path, default=ROOT / "private" / "app.db")
    ap.add_argument("--from-tsv-export", type=Path, default=None, metavar="FILE",
                    help="read sc-* tags from the output of public/api/_export_spotcheck.php")
    ap.add_argument("--user", type=int, action="append", default=[],
                    help="only this user id (repeat for more). Default: every user with an sc- tag")
    a = ap.parse_args(argv)
    key_path = a.key or a.dir / "spotcheck_key.csv"
    if a.from_appdb or a.from_tsv_export:
        for p in ([a.appdb] if a.from_appdb and not a.from_tsv_export else []) + \
                 ([a.from_tsv_export] if a.from_tsv_export else []) + [key_path]:
            if not p.exists():
                print(f"missing {p}", file=sys.stderr)
                return 1
        by_user = read_tsv_export(a.from_tsv_export) if a.from_tsv_export else read_appdb(a.appdb)
        print(tagged_report(by_user, load_key(key_path), set(a.user)))
        return 0
    marks = a.marks or a.dir / "spotcheck_marks.tsv"
    for p in (marks, key_path):
        if not p.exists():
            print(f"missing {p}. Run: python3 tools/eval_sample.py --spotcheck --n 150", file=sys.stderr)
            return 1
    items, bad = load(marks, key_path)
    print(report(items, bad))
    return 0


if __name__ == "__main__":
    sys.exit(main())
