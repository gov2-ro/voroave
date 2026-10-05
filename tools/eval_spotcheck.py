#!/usr/bin/env python3
"""Stage 0 curator spot-check: read the owner's marks and print a one-page result.

    python3 tools/eval_sample.py --spotcheck --n 150      # makes the blind sheet + key
    # The owner fills the `mark` column of data/eval/spotcheck_marks.tsv.
    python3 tools/eval_spotcheck.py                        # prints the result

Marks: bun (good find), meh, slab (dud). A "?" after a mark ("bun?") means unsure.
A lone "?" or a blank cell means no judgment; the word is left out.

It reads two local files only. It never opens ui.db or private/app.db. Stdlib only.
Docs: docs/eval/protocol.md, "Stage 0".
"""
from __future__ import annotations

import argparse
import csv
import random
import sys
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


def load(marks_path: Path, key_path: Path):
    with open(key_path, newline="", encoding="utf-8") as f:
        key = {r["item_id"]: r for r in csv.DictReader(f)}
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
            def num(x):
                return float(x) if x not in ("", None) else 0.0
            items.append({
                "word": k["word"], "mark": mark, "unsure": unsure,
                "rank": int(k["rank"]), "n_total": int(k["n_total"]),
                "score": num(k["score"]), "band": k["score_band"], "seam": k["seam"],
                "modern_occ": num(k["modern_occ"]), "dex_frequency": num(k["dex_frequency"]),
            })
    return items, bad


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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    ap.add_argument("--marks", type=Path, default=None)
    ap.add_argument("--key", type=Path, default=None)
    a = ap.parse_args(argv)
    marks = a.marks or a.dir / "spotcheck_marks.tsv"
    key = a.key or a.dir / "spotcheck_key.csv"
    for p in (marks, key):
        if not p.exists():
            print(f"missing {p}. Run: python3 tools/eval_sample.py --spotcheck --n 150", file=sys.stderr)
            return 1
    items, bad = load(marks, key)
    print(report(items, bad))
    return 0


if __name__ == "__main__":
    sys.exit(main())
