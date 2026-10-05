"""A PHP dev server on a staged copy of public/ (never the repo's own public/)."""
import contextlib
import socket
import subprocess
import time
import urllib.error
import urllib.request


@contextlib.contextmanager
def serve(base):
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    log = open(base / "php-server.log", "wb")
    proc = subprocess.Popen(
        ["php", "-S", f"127.0.0.1:{port}", "-t", str(base / "public"),
         str(base / "tools" / "dev-router.php")],
        stdout=log, stderr=subprocess.STDOUT, cwd=base, start_new_session=True)
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(url + "/robots.txt", timeout=2).close()
                break
            except urllib.error.HTTPError:
                break
            except Exception:
                time.sleep(0.2)
        yield url
    finally:
        proc.terminate()
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            proc.kill()
