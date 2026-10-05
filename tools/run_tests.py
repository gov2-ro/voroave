#!/usr/bin/env python3
"""Strict test runner for the Voroave repository (brief F07).

    python3 tools/run_tests.py                 # every suite, strict
    python3 tools/run_tests.py --portable-only # skip suites that need built data
    python3 tools/run_tests.py --only sync     # suites whose name contains "sync"
    python3 tools/run_tests.py --list          # show the suite table

What it does
  1. Checks prerequisites and stops with an actionable message when one is missing.
  2. Stages a private copy of public/ in a temp directory, with its own
     config.local.php (temp OTIOS_PRIVATE_DIR and a random admin token).
     The repository's private/app.db, secret.key and public/data/*.db are never opened
     for writing. The runner compares their size and mtime before and after.
  3. Starts its own PHP server (dev router, free port) per stage and stops it on exit,
     failure, timeout, Ctrl-C and SIGTERM.
  4. Runs each suite with a timeout. A suite fails on a nonzero exit, a timeout, or a
     SKIP line in its output (a required skip). Use --allow-skips for a lenient run.
  5. Reports portable suites and artifact-dependent suites separately.

To add a suite, add one `Suite(...)` line to SUITES below.
Stdlib only. Needs Python 3.9+.
"""
from __future__ import annotations

import argparse
import atexit
import dataclasses
import os
import re
import secrets
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

CURRENT_CHILD: subprocess.Popen | None = None   # the running suite, killed on a signal
ROOT = Path(__file__).resolve().parent.parent
NODE_MIN = (22, 0)
PHP_MIN = (8, 1)

# Words the synthetic ui.db fixture holds. They are the two words test_store_sync.js
# used to hardcode against the real dictionary; the fixture keeps them durable.
SYNC_WORDS = ["abecedar", "zăbavă"]


@dataclasses.dataclass(frozen=True)
class Suite:
    name: str
    kind: str                 # "py" or "js"
    target: str               # test file or directory, relative to ROOT
    stage: str                # "synthetic" (portable fixture) or "built" (real ui.db/syn.db)
    needs: tuple = ()         # subset of: jsdom, browser, ui_db, syn_db, sqlite3
    timeout: int = 300
    env: tuple = ()           # extra (key, value) pairs


# ---- The suite table. Add a line here to add a suite. ---------------------------------
# stage "synthetic": runs against a tiny generated ui.db; needs no built data (portable).
# stage "built":     runs against a copy of public/data/ui.db (+ syn.db); artifact-dependent.
SUITES = [
    Suite("python (pytest tests)", "py", "tests", "none", (), 600),
    Suite("js sync (synthetic ui.db)", "js", "tests/test_store_sync.js", "synthetic", (), 120,
          (("OTIOS_SYNC_WORDS", ",".join(SYNC_WORDS)),)),
    Suite("js sync races (unit, VM)", "js", "tests/test_store_sync_race.js", "synthetic", (), 120),
    Suite("js lists api", "js", "tests/test_lists_api.js", "built", ("ui_db",)),
    Suite("js game api", "js", "tests/test_game_api.js", "built", ("ui_db",)),
    Suite("js moderation (admin)", "js", "tests/test_moderation.js", "built", ("ui_db",)),
    Suite("js colectii", "js", "tests/test_colectii.js", "built", ("ui_db",)),
    Suite("js class filters", "js", "tests/test_class_filters.js", "built", ("ui_db",)),
    Suite("js editorial", "js", "tests/test_editorial.js", "built", ("ui_db",)),
    Suite("js search scope", "js", "tests/test_search_scope.js", "built", ("ui_db",)),
    Suite("js share meta", "js", "tests/test_share_meta.js", "built", ("ui_db",)),
    Suite("js share seo", "js", "tests/test_share_seo.js", "built", ("ui_db",)),
    Suite("js share view", "js", "tests/test_share_view.js", "built", ("ui_db",)),
    Suite("python statistici route (F04)", "py", "tests/test_statistics_route.py", "none", (), 120),
    Suite("js statistici route (F04)", "js", "tests/test_statistics_route.js", "built", ("ui_db",)),
    Suite("js sinonime", "js", "tests/test_sinonime.js", "built", ("ui_db", "syn_db")),
    Suite("js sinonime states (F01)", "js", "tests/test_sinonime_states.js", "built",
          ("ui_db", "syn_db", "sqlite3")),
    Suite("js senses (browser)", "js", "tests/test_senses.js", "built",
          ("ui_db", "browser", "sqlite3"), 300),
    Suite("js detail parity (F05)", "js", "tests/test_detail_parity.js", "built",
          ("ui_db", "sqlite3")),
    Suite("js ghici (jsdom)", "js", "tests/test_ghici.js", "built", ("ui_db", "jsdom"), 300),
    Suite("js ghici spoilers (browser)", "js", "tests/test_ghici_browser.js", "built",
          ("ui_db", "browser"), 300),
    Suite("js dict tooltip (browser)", "js", "tests/test_dict_tooltip.js", "built",
          ("ui_db", "browser"), 300),
    Suite("js static pages + About prefs (F06)", "js", "tests/test_static_pages.js", "synthetic",
          ("browser",), 120),
    Suite("js footer metrics (browser)", "js", "tests/test_footer_metrics.js", "built",
          ("ui_db", "browser"), 900),
]


def group_of(s: Suite) -> str:
    # The pytest suite reads built data only for a few integration tests, which skip when
    # it is missing. Strict mode turns that skip into a failure, so it is listed as portable
    # (it needs no server) but still requires the artifacts for a full pass.
    return "artifact-dependent" if s.stage == "built" else "portable"


SKIP_RE = re.compile(r"(^\s*SKIP\b)|(\bSKIPPED\b)|(\b\d+ skipped\b)", re.M)


# ---- Prerequisites --------------------------------------------------------------------
class Missing(Exception):
    pass


def run_quiet(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def version_of(cmd, pattern):
    try:
        out = run_quiet(cmd).stdout
    except FileNotFoundError:
        return None
    m = re.search(pattern, out)
    return tuple(int(x) for x in m.groups()) if m else None


def python_for_tests() -> str:
    venv = ROOT / ".venv" / "bin" / "python"
    return str(venv) if venv.exists() else sys.executable


def check_common(problems: list[str]) -> None:
    node = version_of(["node", "-v"], r"v(\d+)\.(\d+)")
    if node is None:
        problems.append("node is not on PATH. Install Node 22 or newer.")
    elif node < NODE_MIN:
        problems.append(f"node {node[0]}.{node[1]} is too old. Install Node {NODE_MIN[0]} or newer.")
    php = version_of(["php", "-v"], r"PHP (\d+)\.(\d+)")
    if php is None:
        problems.append("php is not on PATH. Install PHP 8.1 or newer with pdo_sqlite.")
    else:
        if php < PHP_MIN:
            problems.append(f"php {php[0]}.{php[1]} is too old. Install PHP {PHP_MIN[0]}.{PHP_MIN[1]} or newer.")
        mods = run_quiet(["php", "-m"]).stdout.lower().split()
        for ext in ("pdo_sqlite", "sqlite3", "mbstring", "json"):
            if ext not in mods:
                problems.append(f"PHP extension '{ext}' is missing. Enable it in php.ini.")
    py = python_for_tests()
    r = run_quiet([py, "-c", "import pytest, requests, bs4, lxml, simplemma"])
    if r.returncode != 0:
        problems.append(
            "Python test packages are missing. Run: python3 -m venv .venv && "
            ".venv/bin/pip install -r requirements-test.txt")


def check_node_deps(suites: list[Suite], problems: list[str]) -> None:
    js = [s for s in suites if s.kind == "js"]
    if not js:
        return
    if not (ROOT / "node_modules").is_dir():
        problems.append("node_modules is missing. Run: npm ci")
        return
    # Dependencies must resolve inside the repo, not from ~/node_modules or a global path.
    probe = (
        "const out={};for(const m of ['jsdom','playwright']){try{out[m]=require.resolve(m)}"
        "catch(e){out[m]=null}}console.log(JSON.stringify(out))"
    )
    env = {k: v for k, v in os.environ.items() if k != "NODE_PATH"}
    r = run_quiet(["node", "-e", probe], cwd=ROOT / "tests", env=env)
    import json
    try:
        found = json.loads(r.stdout)
    except ValueError:
        problems.append("Could not probe Node modules: " + r.stderr.strip()[:200])
        return
    for mod in ("jsdom", "playwright"):
        path = found.get(mod)
        if not path:
            problems.append(f"Node package '{mod}' is not installed. Run: npm ci")
        elif not str(path).startswith(str(ROOT / "node_modules")):
            problems.append(f"'{mod}' resolves outside the repository ({path}). Run: npm ci")
    if any("browser" in s.needs for s in js) and found.get("playwright"):
        code = "console.log(require('playwright').chromium.executablePath())"
        r = run_quiet(["node", "-e", code], cwd=ROOT / "tests", env=env)
        exe = r.stdout.strip()
        if not exe or not Path(exe).exists():
            problems.append("The Playwright Chromium build is missing. Run: npx playwright install chromium")


def check_artifacts(suites: list[Suite], problems: list[str]) -> None:
    need = {n for s in suites for n in s.needs}
    data = ROOT / "public" / "data"
    if "ui_db" in need and not (data / "ui.db").is_file():
        problems.append("public/data/ui.db is missing. Build it (tools/build_ui_db.py) "
                        "or run with --portable-only.")
    if "syn_db" in need and not (data / "syn.db").is_file():
        problems.append("public/data/syn.db is missing. Build it (tools/build_syn_db.py) "
                        "or run with --portable-only.")
    if "sqlite3" in need and shutil.which("sqlite3") is None:
        problems.append("The sqlite3 command-line tool is missing. Install it.")


# ---- Staging and server ---------------------------------------------------------------
PROTECTED = [
    ROOT / "private" / "app.db",
    ROOT / "private" / "secret.key",
    ROOT / "public" / "data" / "ui.db",
    ROOT / "public" / "data" / "syn.db",
    ROOT / "data" / "word_ids.tsv",
]


def fingerprint() -> dict:
    out = {}
    for p in PROTECTED:
        try:
            st = p.stat()
            out[str(p)] = (st.st_size, st.st_mtime_ns)
        except FileNotFoundError:
            out[str(p)] = None
    return out


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Stage:
    """One staged copy of public/ with its own private dir, config and PHP server."""

    def __init__(self, tmp: Path, name: str, token: str):
        self.name = name
        self.token = token
        self.base = tmp / name
        self.public = self.base / "public"
        self.private = self.base / "private"
        self.proc: subprocess.Popen | None = None
        self.port = 0
        self.log = self.base / "php-server.log"

    def build(self, synthetic: bool) -> None:
        def ignore(_dir, names):
            skip = {"config.local.php", "__pycache__"}
            if Path(_dir).name == "data":
                skip |= set(names)           # data/ is filled below
            return [n for n in names if n in skip or n.endswith((".log", "-wal", "-shm"))]
        shutil.copytree(ROOT / "public", self.public, ignore=ignore)
        (self.public / "data").mkdir(exist_ok=True)
        (self.base / "tools").mkdir()
        shutil.copy(ROOT / "tools" / "dev-router.php", self.base / "tools" / "dev-router.php")
        self.private.mkdir(mode=0o700)
        if synthetic:
            con = sqlite3.connect(self.public / "data" / "ui.db")
            con.execute("CREATE TABLE words (word TEXT PRIMARY KEY)")
            con.executemany("INSERT INTO words VALUES (?)", [(w,) for w in SYNC_WORDS])
            con.commit()
            con.close()
        else:
            for f in ("ui.db", "syn.db"):
                src = ROOT / "public" / "data" / f
                if src.is_file():
                    shutil.copy(src, self.public / "data" / f)
        # The staged config is the only config the staged app can load.
        (self.public / "api" / "config.local.php").write_text(
            "<?php\ndeclare(strict_types=1);\n"
            f"define('OTIOS_PRIVATE_DIR', {str(self.private)!r});\n"
            f"define('OTIOS_ADMIN_TOKEN', {self.token!r});\n"
        )
        assert Path(self.private).resolve() != (ROOT / "private").resolve()
        assert (self.base).resolve() != ROOT.resolve()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> None:
        self.port = free_port()
        logf = open(self.log, "wb")
        self.proc = subprocess.Popen(
            ["php", "-S", f"127.0.0.1:{self.port}", "-t", str(self.public),
             str(self.base / "tools" / "dev-router.php")],
            stdout=logf, stderr=subprocess.STDOUT, start_new_session=True, cwd=self.base,
        )
        deadline = time.time() + 20
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise Missing(f"PHP server for stage '{self.name}' exited early:\n"
                              + self.log.read_text(errors="replace")[-800:])
            try:
                urllib.request.urlopen(self.url + "/robots.txt", timeout=2).close()
                return
            except urllib.error.HTTPError:
                return
            except OSError:
                time.sleep(0.15)
        raise Missing(f"PHP server for stage '{self.name}' was not ready after 20 s.")

    def stop(self) -> None:
        p, self.proc = self.proc, None
        if p is None or p.poll() is not None:
            return
        try:
            os.killpg(p.pid, signal.SIGTERM)
            p.wait(timeout=5)
        except Exception:
            try:
                os.killpg(p.pid, signal.SIGKILL)
                p.wait(timeout=5)
            except Exception:
                pass


# ---- Running --------------------------------------------------------------------------
def run_suite(s: Suite, stage: Stage | None, token: str, allow_skips: bool, verbose: bool) -> dict:
    env = {k: v for k, v in os.environ.items() if k != "NODE_PATH"}
    env["OTIOS_STRICT"] = "1"
    if s.kind == "py":
        cmd = [python_for_tests(), "-m", "pytest", s.target, "-q", "-rs", "-p", "no:cacheprovider"]
    else:
        cmd = ["node", s.target]
        assert stage is not None
        env["OTIOS_TEST_URL"] = stage.url
        env["OTIOS_TEST_ISOLATED"] = "1"
        env["OTIOS_ADMIN_TOKEN"] = token
        env["OTIOS_TEST_DATA_DIR"] = str(stage.public / "data")
        env["OTIOS_PRIVATE_DIR"] = str(stage.private)
    env.update(dict(s.env))
    t0 = time.time()
    reason = ""
    try:
        proc = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, start_new_session=True)
        global CURRENT_CHILD
        CURRENT_CHILD = proc
        try:
            out, _ = proc.communicate(timeout=s.timeout)
            code = proc.returncode
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            out, _ = proc.communicate()
            code = -9
            reason = f"timeout after {s.timeout} s"
    except FileNotFoundError as e:
        out, code, reason = "", 127, f"cannot start: {e}"
    if not reason and code != 0:
        reason = f"exit code {code}"
    if not reason and not allow_skips and SKIP_RE.search(out):
        lines = [ln.strip() for ln in out.splitlines() if SKIP_RE.search(ln)]
        reason = "required check skipped: " + "; ".join(lines[:3])
    status = "PASS" if not reason else "FAIL"
    if reason and allow_skips is False and "skipped" in reason:
        status = "FAIL"
    tail = "\n".join(out.splitlines()[-40:])
    if verbose or status == "FAIL":
        print(out if verbose else tail)
    counts = ""
    m = re.search(r"(\d+) passed", out)
    if m:
        counts = f"{m.group(1)} passed"
    else:
        n_pass, n_fail = len(re.findall(r"\bPASS\b", out)), len(re.findall(r"\bFAIL\b", out))
        counts = f"{n_pass} PASS lines, {n_fail} FAIL lines"
    return {"suite": s, "status": status, "reason": reason, "secs": time.time() - t0, "counts": counts}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", help="run suites whose name contains this text")
    ap.add_argument("--portable-only", action="store_true", help="skip artifact-dependent suites (partial run)")
    ap.add_argument("--allow-skips", action="store_true", help="do not fail on SKIP lines (not for acceptance)")
    ap.add_argument("--timeout", type=int, help="override every suite's timeout, in seconds")
    ap.add_argument("--keep", action="store_true", help="keep the temp directory")
    ap.add_argument("-v", "--verbose", action="store_true", help="print all suite output")
    ap.add_argument("--list", action="store_true", help="list suites and exit")
    args = ap.parse_args()

    if args.list:
        for s in SUITES:
            print(f"{group_of(s):19} {s.name:32} needs={','.join(s.needs) or '-'}")
        return 0

    suites = [dataclasses.replace(s, timeout=args.timeout) if args.timeout else s
              for s in SUITES if not args.only or args.only.lower() in s.name.lower()]
    if not suites:
        print("No suite matches --only.", file=sys.stderr)
        return 2
    skipped_groups = []
    if args.portable_only:
        skipped_groups = [s for s in suites if group_of(s) == "artifact-dependent"]
        suites = [s for s in suites if group_of(s) == "portable"]

    problems: list[str] = []
    check_common(problems)
    check_node_deps(suites, problems)
    check_artifacts(suites, problems)
    if problems:
        print("Prerequisites are not met:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 3

    before = fingerprint()
    tmp = Path(tempfile.mkdtemp(prefix="otios-test-"))
    token = secrets.token_hex(24)
    stages: dict[str, Stage] = {}

    def cleanup():
        if CURRENT_CHILD is not None and CURRENT_CHILD.poll() is None:
            try:
                os.killpg(CURRENT_CHILD.pid, signal.SIGKILL)
            except OSError:
                pass
        for st in stages.values():
            st.stop()
        if not args.keep:
            shutil.rmtree(tmp, ignore_errors=True)

    atexit.register(cleanup)

    def on_signal(signum, _frame):
        print(f"\nSignal {signum}: stopping servers.", file=sys.stderr)
        cleanup()
        os._exit(130)

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    results = []
    try:
        for name in ("synthetic", "built"):
            if any(s.stage == name for s in suites):
                st = Stage(tmp, name, token)
                stages[name] = st
                st.build(synthetic=(name == "synthetic"))
                st.start()
                print(f"[stage {name}] PHP server on {st.url}, private dir {st.private}")
        for s in suites:
            print(f"\n=== {s.name} ({group_of(s)}) ===", flush=True)
            r = run_suite(s, stages.get(s.stage), token, args.allow_skips, args.verbose)
            print(f"--- {r['status']}  {r['counts']}  {r['secs']:.1f}s  {r['reason']}", flush=True)
            results.append(r)
        # Proof that the staged app wrote to the temp private dir and not elsewhere.
        for st in stages.values():
            if st.name == "built" or st.name == "synthetic":
                if not (st.private / "app.db").exists():
                    print(f"note: stage {st.name} never created app.db (no API suite wrote to it)")
    except Missing as e:
        print(f"Setup failed: {e}", file=sys.stderr)
        return 3
    finally:
        cleanup()

    after = fingerprint()
    changed = [p for p in before if before[p] != after[p]]

    print("\n================ SUMMARY ================")
    for grp in ("portable", "artifact-dependent"):
        rows = [r for r in results if group_of(r["suite"]) == grp]
        if not rows:
            continue
        print(f"\n{grp.upper()} suites")
        for r in rows:
            print(f"  {r['status']:4}  {r['suite'].name:34} {r['counts']}  {r['reason']}")
    if skipped_groups:
        print("\nNOT RUN (--portable-only): " + ", ".join(s.name for s in skipped_groups))
        print("PARTIAL RUN: this is not the full acceptance check.")
    failed = [r for r in results if r["status"] != "PASS"]
    if changed:
        print("\nISOLATION FAILURE: protected files changed during the run:")
        for p in changed:
            print(f"  {p}: {before[p]} -> {after[p]}")
    print(f"\nProtected files unchanged: {'NO' if changed else 'yes'}")
    print(f"Result: {'FAIL' if failed or changed else 'PASS'} "
          f"({len(results) - len(failed)}/{len(results)} suites passed)")
    return 1 if failed or changed else 0


if __name__ == "__main__":
    sys.exit(main())
