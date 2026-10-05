"""Guards for marking the Stage 0 spot-check in the web UI (F09).

Every app.db here is synthetic and lives in tmp. The staged PHP copy has its own
config.local.php, so nothing opens private/app.db or writes public/data/*.db.
"""
import hashlib
import json
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(Path(__file__).parent))
import eval_sample as ev  # noqa: E402
import eval_spotcheck as sc  # noqa: E402
from test_eval_sample import make_db  # noqa: E402

REAL_UI = ROOT / "public" / "data" / "ui.db"
HAVE_PHP = shutil.which("php") is not None


def stage(tmp: Path, with_ui_db: bool) -> Path:
    """A copy of public/ with its own config.local.php and an empty private dir."""
    base = tmp / "stage"
    pub, priv = base / "public", base / "private"

    def ignore(d, names):
        skip = {"config.local.php", "__pycache__"}
        if Path(d).name == "data":
            skip |= set(names)
        return [n for n in names if n in skip or n.endswith((".log", "-wal", "-shm"))]
    shutil.copytree(ROOT / "public", pub, ignore=ignore)
    (pub / "data").mkdir(exist_ok=True)
    (base / "tools").mkdir()
    shutil.copy(ROOT / "tools" / "dev-router.php", base / "tools" / "dev-router.php")
    priv.mkdir(mode=0o700)
    if with_ui_db:
        shutil.copy(REAL_UI, pub / "data" / "ui.db")
    (pub / "api" / "config.local.php").write_text(
        f"<?php\ndeclare(strict_types=1);\ndefine('OTIOS_PRIVATE_DIR', {str(priv)!r});\n")
    assert priv.resolve() != (ROOT / "private").resolve()
    return base


def make_app_db(base: Path) -> Path:
    """Create the real schema by running the app's own migration in the staged copy."""
    api = base / "public" / "api"
    subprocess.run(["php", "-r", f"require '{api}/_appdb.php'; app_db();"], check=True,
                   capture_output=True, cwd=base)
    path = base / "private" / "app.db"
    assert path.is_file()
    return path


def put(db: Path, user, word, tags, deleted=0, bookmarked=0, note=""):
    con = sqlite3.connect(db)
    con.execute("INSERT OR REPLACE INTO annotations (user_id, word, bookmarked, note, tags, "
                "updated_at, seq, deleted) VALUES (?,?,?,?,?,?,?,?)",
                (user, word, bookmarked, note, json.dumps(tags), "2026-10-05T00:00:00Z", 1, deleted))
    con.commit()
    con.close()


@pytest.fixture
def app(tmp_path):
    if not HAVE_PHP:
        pytest.skip("php not on PATH")
    base = stage(tmp_path, with_ui_db=False)
    return base, make_app_db(base)


def fingerprint(path: Path):
    files = [path] + [Path(str(path) + s) for s in ("-wal", "-shm")]
    return [(f.name, f.stat().st_mtime_ns, f.stat().st_size,
             hashlib.sha256(f.read_bytes()).hexdigest()) for f in files if f.exists()]


def test_reader_takes_sc_tags_only_and_leaves_the_file_alone(app):
    _, db = app
    put(db, 1, "alfa", ["sc-bun"])
    put(db, 1, "beta", ["fav", "lol", "meh", "salut"], bookmarked=1)   # no sc- tag
    put(db, 1, "gama", ["sc-slab"], deleted=1)                         # deleted row
    put(db, 1, "delta", ["meh", "sc-meh-q"])
    put(db, 2, "alfa", ["sc-bun-q"], note="private note sc-secret")
    before = fingerprint(db)[0]
    got = sc.read_appdb(db)
    # SQLite may create an empty -wal/-shm pair for a WAL file; the database itself stays as it was.
    assert fingerprint(db)[0] == before
    assert all(Path(str(db) + s).stat().st_size == 0 for s in ("-wal",) if Path(str(db) + s).exists())
    assert {u: dict(w) for u, w in got.items()} == {
        1: {"alfa": ["sc-bun"], "delta": ["sc-meh-q"]},
        2: {"alfa": ["sc-bun-q"]},
    }


def test_reader_sees_committed_rows_still_in_the_wal(app):
    _, db = app
    writer = sqlite3.connect(db)
    mode = writer.execute("PRAGMA journal_mode=WAL").fetchone()[0]
    writer.execute("PRAGMA wal_autocheckpoint=0")
    writer.execute("INSERT INTO annotations (user_id, word, tags, updated_at, seq, deleted) "
                   "VALUES (5, 'omega', '[\"sc-slab\"]', 'x', 1, 0)")
    writer.commit()                      # committed, not checkpointed, writer still open
    try:
        assert mode == "wal"
        assert Path(str(db) + "-wal").stat().st_size > 0
        assert dict(sc.read_appdb(db)[5]) == {"omega": ["sc-slab"]}
    finally:
        writer.close()


def test_tag_rules():
    assert sc.parse_sc_tag("sc-bun") == ("bun", False)
    assert sc.parse_sc_tag("SC-Slab-q") == ("slab", True)
    for t in ("sc-bun?", "sc-x", "bun", "sc-bun-q-q", "fav", ""):
        assert sc.parse_sc_tag(t) is None
    assert sc.resolve_tags(["sc-bun"]) == ("bun", False, False)
    assert sc.resolve_tags(["sc-bun", "sc-bun-q"]) == ("bun", True, False)      # any -q = unsure
    assert sc.resolve_tags(["sc-bun", "sc-slab"]) == (None, False, True)        # conflict
    assert sc.resolve_tags(["fav"]) == (None, False, False)


def test_kappa_and_agreement_on_a_constructed_case():
    a = ["bun"] * 4 + ["slab"] * 2 + ["meh"] * 2 + ["bun", "slab"]
    b = ["bun"] * 4 + ["slab"] * 2 + ["meh"] * 2 + ["slab", "bun"]
    k = sc.cohen_kappa(list(zip(a, b)))
    assert k == pytest.approx((0.8 - 0.38) / 0.62)
    assert sc.cohen_kappa([("bun", "bun")] * 3) is None          # chance agreement 1
    assert sc.cohen_kappa([]) is None
    words = [f"w{i}" for i in range(10)]
    lines = sc.agreement_lines({1: dict(zip(words, a)), 2: dict(zip(words, b)),
                                3: {"zz": "bun"}})
    assert "10 words in common, agree 8 (80%), Cohen's kappa 0.68" in lines[0]
    assert "no words judged by both" in lines[1] and "no words judged by both" in lines[2]


def test_end_to_end_report_by_marker_and_export_parity(app, tmp_path):
    base, db = app
    ui = tmp_path / "u.db"
    make_db(ui)
    out = tmp_path / "o"
    ev.run_spotcheck(ui, out, 30, ev.SPOT_SEED)
    key = sc.load_key(out / "spotcheck_key.csv")
    words = sorted(k["word"] for k in key.values())
    for i, w in enumerate(words[:8]):
        put(db, 1, w, ["sc-bun" if i % 2 else "sc-slab"])
        put(db, 2, w, ["sc-bun" if i % 3 else "sc-slab"])
    put(db, 1, words[9], ["sc-bun", "sc-meh"])                    # conflict
    put(db, 1, "not-in-sample", ["sc-bun"])
    put(db, 1, words[10], ["fav", "meh"])                          # not a spot-check mark
    direct = sc.tagged_report(sc.read_appdb(db), key, set())
    assert "Markers found: 1, 2 (all users holding an sc- tag)" in direct
    assert "===== Marker: user 1 =====" in direct and "===== Marker: user 2 =====" in direct
    assert "Judged: 8" in direct
    assert "conflicting tags" in direct and "not in the sample" in direct
    assert "Agreement between markers" in direct and "8 words in common" in direct
    only2 = sc.tagged_report(sc.read_appdb(db), key, {2})
    assert "Marker: user 1" not in only2 and "Marker: user 2" in only2

    # The CLI export script prints only (user_id, word, sc- tag).
    res = subprocess.run(["php", str(base / "public" / "api" / "_export_spotcheck.php")],
                         capture_output=True, text=True, cwd=base)
    assert res.returncode == 0, res.stderr
    lines = res.stdout.splitlines()
    assert lines[0] == "user_id\tword\ttag"
    assert all(len(ln.split("\t")) == 3 for ln in lines)
    assert all(ln.split("\t")[2].startswith("sc-") for ln in lines[1:])
    assert "secret" not in res.stdout and "fav" not in res.stdout
    tsv = tmp_path / "export.tsv"
    tsv.write_text(res.stdout, encoding="utf-8")
    via_file = sc.tagged_report(sc.read_tsv_export(tsv), key, set())
    assert via_file == direct                       # same figures from either route


def test_export_script_is_inert_over_http(app):
    base, _ = app
    from tools_server import serve
    with serve(base) as url:
        try:
            urllib.request.urlopen(url + "/api/_export_spotcheck.php", timeout=10)
            code = 200
        except urllib.error.HTTPError as e:
            code = e.code
    assert code == 404


def test_tsv_export_rejects_a_wrong_header(tmp_path):
    p = tmp_path / "x.tsv"
    p.write_text("a\tb\tc\n1\tw\tsc-bun\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        sc.read_tsv_export(p)


def test_pack_ids_known_values():
    assert ev.pack_ids([1, 35, 36, 396 * 1]) == "1.1.z.10." + ev._base36(396)
    assert ev.pack_ids([]) == ""
    assert ev.spotcheck_link("1.a") == "/?w=1.a&sort=alpha&editorial=show"


@pytest.mark.skipif(not REAL_UI.exists() or not HAVE_PHP, reason="needs ui.db and php")
def test_playlist_link_shows_exactly_the_sample_in_alpha_order(tmp_path):
    from tools_server import serve
    out = tmp_path / "o"
    summary = ev.run_spotcheck(REAL_UI, out, 150, ev.SPOT_SEED)
    link = summary["link"]
    assert (out / "spotcheck_link.txt").read_text(encoding="utf-8").strip() == link
    key = sc.load_key(out / "spotcheck_key.csv")
    names = sorted(k["word"] for k in key.values())
    assert len(names) == 150
    qs = urllib.parse.parse_qs(urllib.parse.urlsplit(link).query)
    packed = qs["w"][0]
    base = stage(tmp_path, with_ui_db=True)
    with serve(base) as url:
        # Codec parity: PHP unpack_words() reads what Python packed, in the same order.
        got = json.load(urllib.request.urlopen(f"{url}/api/pack.php?w={packed}", timeout=20))
        assert got["words"] == names
        # And PHP pack_words() writes the same string back.
        req = urllib.request.Request(
            url + "/api/pack.php", data=json.dumps({"words": names}).encode(),
            headers={"Content-Type": "application/json", "Origin": url})
        assert json.load(urllib.request.urlopen(req, timeout=20))["w"] == packed
        # The list: the link's own params, sent to the list endpoint, with the default
        # filter sheet (which hides most words) left untouched.
        html = urllib.request.urlopen(f"{url}/api/search.php?{urllib.parse.urlsplit(link).query}",
                                      timeout=30).read().decode()
        shown = re.findall(r'class="word-row[^"]*"[^>]*?data-word="([^"]+)"', html)
        if not shown:
            shown = re.findall(r'data-word="([^"]+)"', html)
        import html as h
        shown = [h.unescape(x) for x in shown]
        assert shown == names
