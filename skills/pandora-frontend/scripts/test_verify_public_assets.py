"""Deterministic local checks; no external server, provider or private data is used."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest

ART = b'<svg xmlns="http://www.w3.org/2000/svg"><circle r="2"/></svg>'


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/absent.svg":
            self.send_response(404)
            self.end_headers()
            return
        if self.path == "/redirect.svg":
            self.send_response(302)
            self.send_header("Location", "/good.svg")
            self.end_headers()
            return
        body = b"changed" if self.path == "/changed.svg" else ART
        self.send_response(200)
        self.send_header("Content-Type", "text/html" if self.path == "/wrong.svg" else "image/svg+xml")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


class AssetChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="pandora-assets-test-")
        cls.root = Path(cls.temporary.name).resolve()
        if cls.root.parent != Path(tempfile.gettempdir()).resolve():
            raise RuntimeError("Unexpected disposable fixture directory")
        for name in ("good.svg", "wrong.svg", "changed.svg", "redirect.svg"):
            (cls.root / name).write_bytes(ART)
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.temporary.cleanup()

    def check(self, *args):
        return subprocess.run([sys.executable, str(Path(__file__).with_name("verify_public_assets.py")), "--public-dir", str(self.root), *args], capture_output=True, text=True, timeout=10)

    def test_real_bytes_mime_and_missing_404(self):
        result = self.check("--base-url", self.base, "--asset", "good.svg", "--missing", "absent.svg")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS missing absent.svg: HTTP 404", result.stdout)

    def test_html_200_is_not_an_asset_success(self):
        self.assertNotEqual(self.check("--base-url", self.base, "--asset", "wrong.svg").returncode, 0)

    def test_byte_changes_and_redirects_fail(self):
        for asset in ("changed.svg", "redirect.svg"):
            with self.subTest(asset=asset):
                self.assertNotEqual(self.check("--base-url", self.base, "--asset", asset).returncode, 0)

    def test_spa_200_is_not_missing_404(self):
        self.assertNotEqual(self.check("--base-url", self.base, "--asset", "good.svg", "--missing", "spa.svg").returncode, 0)

    def test_path_escape_and_credential_url_are_rejected(self):
        self.assertNotEqual(self.check("--base-url", self.base, "--asset", "../escape.svg").returncode, 0)
        result = self.check("--base-url", self.base.replace("://", "://tester:secret@"), "--asset", "good.svg")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("secret", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
