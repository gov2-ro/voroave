"""F04: the application statistics route is /statistici, not the host-reserved /stats.

Portable. It stages tiny copies of the real .htaccess and dev router with a probe
stats.php, so it needs no ui.db and never loads the real application or any app.db.
The Apache test is opt-in (`pytest tests -m apache`), because it needs a local httpd
with mod_rewrite. The required run deselects it; when selected without httpd, it skips.
"""
import os
import re
import shutil
import signal
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HTACCESS = ROOT / "public" / ".htaccess"
ROUTER = ROOT / "tools" / "dev-router.php"
PROBE = '<?php echo "APP:" . ($_SERVER["QUERY_STRING"] ?? "") . "|" . ($_SERVER["SCRIPT_NAME"] ?? "");'


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


OPENER = urllib.request.build_opener(NoRedirect)


def get(url, data=None):
    try:
        r = OPENER.open(urllib.request.Request(url, data=data), timeout=5)
        return r.status, r.read().decode("utf-8", "replace"), r.headers
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace"), e.headers


def wait_up(url, proc):
    for _ in range(100):
        if proc.poll() is not None:
            raise RuntimeError("server exited early")
        try:
            get(url)
            return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError("server not ready")


def stop(proc):
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=5)
    except Exception:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except Exception:
            pass


@pytest.fixture(scope="module")
def router_site():
    """Docroot with a probe app at / and at /sub/, plus a provider-style stats/ at /prov/."""
    tmp = Path(tempfile.mkdtemp(prefix="otios-f04-"))
    pub = tmp / "public"
    for d in ("", "sub", "prov"):
        (pub / d).mkdir(parents=True, exist_ok=True)
    (pub / "stats.php").write_text(PROBE)
    (pub / "sub" / "stats.php").write_text(PROBE)
    (pub / "prov" / "stats.php").write_text(PROBE)
    (pub / "prov" / "stats").mkdir()
    (pub / "prov" / "stats" / "index.html").write_text("provider report")
    (pub / "despre.html").write_text("despre page")
    (tmp / "tools").mkdir()
    shutil.copy(ROUTER, tmp / "tools" / "dev-router.php")
    port = free_port()
    proc = subprocess.Popen(
        ["php", "-S", f"127.0.0.1:{port}", "-t", str(pub), str(tmp / "tools" / "dev-router.php")],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True, cwd=tmp)
    base = f"http://127.0.0.1:{port}"
    try:
        wait_up(base + "/despre", proc)
        yield base
    finally:
        stop(proc)
        shutil.rmtree(tmp, ignore_errors=True)


def test_htaccess_rule_precedes_generic_rules():
    text = HTACCESS.read_text()
    rule = re.search(r"^\s*RewriteRule\s+\^statistici/\?\$\s+stats\.php\s+\[L\]\s*$", text, re.M)
    assert rule, "explicit /statistici rule is missing"
    generic = text.index("RewriteRule ^(.+?)/?$ $1.php")
    assert rule.start() < generic, "the /statistici rule must come before the generic rules"
    assert "QSD" not in rule.group(0) and "R=" not in rule.group(0), "must be internal and keep the query"
    # No broad extension-removal redirect was added.
    assert not re.search(r"RewriteRule\s+\^\(\.\+.*\.php.*\[R", text)


def test_router_serves_statistici(router_site):
    code, body, _ = get(router_site + "/statistici")
    assert code == 200 and body.startswith("APP:")
    assert get(router_site + "/statistici/")[0] == 200


def test_router_keeps_legacy_stats_php(router_site):
    code, body, _ = get(router_site + "/stats.php")
    assert code == 200 and body.startswith("APP:")


def test_router_keeps_query_string(router_site):
    code, body, _ = get(router_site + "/statistici?word_tier=forgotten&pos=s.f.")
    assert code == 200 and body.startswith("APP:word_tier=forgotten&pos=s.f.")


def test_router_subfolder_prefix(router_site):
    code, body, _ = get(router_site + "/sub/statistici?x=1")
    assert code == 200 and body == "APP:x=1|/sub/stats.php"


def test_router_does_not_redirect(router_site):
    code, _, headers = get(router_site + "/statistici")
    assert code == 200 and "Location" not in headers


def test_statistici_works_beside_a_real_stats_directory(router_site):
    # The collision: a real /prov/stats/ directory serves itself and shadows /prov/stats.
    assert "provider report" in get(router_site + "/prov/stats/")[1]
    code, body, _ = get(router_site + "/prov/statistici")
    assert code == 200 and body.startswith("APP:")


def test_other_clean_urls_unchanged(router_site):
    code, body, _ = get(router_site + "/despre")
    assert code == 200 and body == "despre page"
    assert get(router_site + "/nu-exista")[0] == 404


def test_post_to_statistici_is_not_redirected(router_site):
    code, _, headers = get(router_site + "/statistici", data=b"a=1")
    assert code == 200 and "Location" not in headers


# ---- Apache, when the host has it ------------------------------------------------------
def find_apache():
    exe = shutil.which("httpd")
    if not exe:
        return None
    root = None
    for line in subprocess.run([exe, "-V"], capture_output=True, text=True).stdout.splitlines():
        m = re.search(r'HTTPD_ROOT="([^"]+)"', line)
        if m:
            root = Path(m.group(1))
    cands = [Path("/usr/lib/apache2/modules"), Path("/usr/libexec/apache2")]
    if root:
        cands += [root / "lib" / "httpd" / "modules", root / "modules",
                  root.parent.parent / "lib" / "httpd" / "modules"]
    mod = next((c for c in cands if (c / "mod_rewrite.so").is_file()), None)
    if mod is None:
        return None
    return exe, mod


@pytest.mark.apache
def test_apache_rewrite_root_and_subfolder():
    found = find_apache()
    if not found:
        pytest.skip("SKIP httpd with mod_rewrite is not installed; the .htaccess rule is unverified on Apache")
    exe, mod = found
    tmp = Path(tempfile.mkdtemp(prefix="otios-f04-apache-"))
    try:
        doc = tmp / "www"
        (doc / "sub").mkdir(parents=True)
        (doc / "prov" / "stats").mkdir(parents=True)
        for d in (doc, doc / "sub", doc / "prov"):
            (d / ".htaccess").write_text(HTACCESS.read_text())
            (d / "stats.php").write_text("APP stats\n")
        (doc / "despre.html").write_text("despre page\n")
        (doc / "prov" / "stats" / "index.html").write_text("provider report\n")
        port = free_port()
        conf = tmp / "httpd.conf"
        mods = ["mpm_prefork", "unixd", "authz_core", "dir", "mime", "rewrite", "alias"]
        lines = [f"LoadModule {m}_module {mod}/mod_{m}.so" for m in mods
                 if (mod / f"mod_{m}.so").is_file()]
        lines += [
            f"ServerRoot {tmp}", f"Listen 127.0.0.1:{port}", "ServerName localhost",
            f"PidFile {tmp}/httpd.pid", f"ErrorLog {tmp}/error.log", "LogLevel warn",
            f"DocumentRoot {doc}", "DirectoryIndex index.html",
            f'<Directory "{doc}">', "  AllowOverride All", "  Require all granted", "</Directory>",
            "TypesConfig /dev/null", "AddType text/plain .php .html",
        ]
        conf.write_text("\n".join(lines) + "\n")
        proc = subprocess.Popen([exe, "-X", "-f", str(conf)], stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, start_new_session=True)
        base = f"http://127.0.0.1:{port}"
        try:
            wait_up(base + "/despre", proc)
            for prefix in ("", "/sub", "/prov"):
                code, body, headers = get(f"{base}{prefix}/statistici?x=1")
                assert code == 200 and body == "APP stats\n", (prefix, code, body)
                assert "Location" not in headers
            assert get(base + "/stats.php")[1] == "APP stats\n"
            assert get(base + "/despre")[1] == "despre page\n"
            # The real directory keeps shadowing /prov/stats; that is the host collision.
            assert "provider report" in get(base + "/prov/stats/")[1]
        finally:
            stop(proc)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
