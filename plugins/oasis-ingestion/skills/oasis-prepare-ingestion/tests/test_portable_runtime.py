"""Synthetic-only tests. Set OASIS_TEST_VENV to an environment built by setup."""

import csv
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from run_import import read_config  # noqa: E402  # ty: ignore[unresolved-import]
from validate_manifest import FIELDS  # noqa: E402  # ty: ignore[unresolved-import]

KEY = "SYNTHETIC-ONLY-NOT-A-SECRET"
UID = "00000000-0000-4000-8000-000000000001"


class SyntheticServer(ThreadingHTTPServer):
    calls: list[tuple[str, str]]
    redirect: bool
    fail_upload: bool


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass

    def do_GET(self):
        self.handle_request()

    def do_POST(self):
        self.handle_request()

    def handle_request(self):
        server = cast(SyntheticServer, self.server)
        server.calls.append((self.command, self.path))
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if self.headers.get("X-API-Key") != KEY:
            self.send_response(401)
            self.end_headers()
            return
        if server.redirect:
            self.send_response(302)
            self.send_header("Location", "/redirect-target")
            self.end_headers()
            return
        if self.path.endswith("/health"):
            data = {"status": "ok"}
        elif self.path.endswith("/file-types"):
            data = []
        elif self.path.endswith("/learners/bulk"):
            data = {
                "summary": {
                    "total": 1,
                    "created": 1,
                    "updated": 0,
                    "invalid": 0,
                    "duplicates": 0,
                    "errors": 0,
                },
                "results": [
                    {
                        "index": 0,
                        "email": "demo@example.org",
                        "learner_id": UID,
                        "learner_name": "Demo",
                        "learner_entry": "created",
                        "status": 201,
                        "message": "created",
                    }
                ],
            }
        elif self.path.endswith("/cohorts"):
            data = {
                "cohort_id": UID,
                "cohort_name": "SYNTHETIC",
                "cohort_entry": "created",
                "summary": {
                    "total": 1,
                    "linked": 1,
                    "already_linked": 0,
                    "not_found": 0,
                    "duplicates": 0,
                    "invalid": 0,
                    "errors": 0,
                },
                "results": [
                    {
                        "index": 0,
                        "email": "demo@example.org",
                        "learner_id": UID,
                        "learner_name": "Demo",
                        "link_entry": "linked",
                        "status": 201,
                        "message": "linked",
                    }
                ],
            }
        elif self.path.endswith("/encounters"):
            data = {
                "encounter_id": UID,
                "encounter_key": "synthetic-key",
                "encounter_date": "09/10/2026",
                "case_id": UID,
                "case_name": "Demo Case",
                "activity_id": UID,
                "activity_name": "Demo OSCE",
                "cohort_id": UID,
                "cohort_name": "SYNTHETIC",
                "learners": [
                    {"learner_id": UID, "learner_name": "Demo", "email": "demo@example.org"}
                ],
                "encounter_entry": "created",
                "case_entry": "created",
                "activity_entry": "created",
            }
        elif self.path.endswith("/upload-by-id"):
            if server.fail_upload:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(
                    json.dumps({"title": "Synthetic failure " + KEY, "status": 500}).encode()
                )
                return
            data = {"file_name": "note.txt", "status": 201, "message": "created", "file_id": UID}
        else:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())


class PortableTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="oasis-portable-test-")
        self.root = Path(self.temp.name)
        self.inputs = self.root / "inputs"
        self.inputs.mkdir()
        (self.inputs / "note.txt").write_text("Synthetic note, no patient or learner data.\n")
        self.manifest = self.root / "ingest.csv"
        with self.manifest.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(FIELDS)
            w.writerow(
                [
                    "SYNTHETIC",
                    "Demo",
                    "demo@example.org",
                    "Demo OSCE",
                    "Demo Case",
                    "09/10/2026",
                    "",
                    "note.txt",
                    "notes_txt",
                ]
            )
        self.private = self.root / "private"
        self.private.mkdir(mode=0o700)
        self.config = self.private / ".env"
        self.config.write_text(
            "ELEPHANT_API_KEY=" + KEY + "\nELEPHANT_API_URL=https://example.org\n"
        )
        self.config.chmod(0o600)

    def tearDown(self):
        self.temp.cleanup()

    def run_cmd(self, action, name, extra=()):
        cmd = [
            sys.executable,
            str(ROOT / "scripts/run_import.py"),
            action,
            "--receipt-dir",
            str(self.root / name),
        ]
        if action != "check-connection":
            cmd += ["--csv", str(self.manifest), "--data-dir", str(self.inputs)]
        return subprocess.run(cmd + list(extra), capture_output=True, text=True)

    def start_server(self):
        env = os.environ.get("OASIS_TEST_VENV")
        if not env:
            self.skipTest("Set OASIS_TEST_VENV for installed-SDK transport tests")
        server = SyntheticServer(("127.0.0.1", 0), Handler)
        server.calls = []
        server.redirect = False
        server.fail_upload = False
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        url = f"http://127.0.0.1:{server.server_port}"
        self.config.write_text("ELEPHANT_API_KEY=" + KEY + "\nELEPHANT_API_URL=" + url + "\n")
        return server, ["--venv", env, "--config", str(self.config), "--expected-url", url]

    def test_literal_private_config(self):
        self.config.write_text(
            "ELEPHANT_API_KEY='$(never-run-this)'\nELEPHANT_API_URL=https://example.org\n"
        )
        self.assertEqual(read_config(self.config)["ELEPHANT_API_KEY"], "$(never-run-this)")

    def test_duplicate_config_rejected(self):
        with self.config.open("a") as f:
            f.write("ELEPHANT_API_KEY=second\n")
        with self.assertRaises(ValueError):
            read_config(self.config)

    @unittest.skipUnless(os.name == "posix", "POSIX mode check")
    def test_public_config_rejected(self):
        self.config.chmod(0o644)
        with self.assertRaises(ValueError):
            read_config(self.config)

    def test_dry_run_and_no_overwrite(self):
        r = self.run_cmd("dry-run", "preview")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.root / "preview/validation.json").is_file())
        self.assertNotEqual(self.run_cmd("dry-run", "preview").returncode, 0)

    def test_invalid_manifest(self):
        (self.inputs / "note.txt").unlink()
        self.assertNotEqual(self.run_cmd("dry-run", "preview").returncode, 0)
        self.assertFalse((self.root / "preview").exists())

    def test_connection_read_only(self):
        server, args = self.start_server()
        r = self.run_cmd("check-connection", "connection", args)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(server.calls, [("GET", "/api/v1/health"), ("GET", "/api/v1/file-types")])

    def test_target_mismatch(self):
        server, args = self.start_server()
        args[-1] = "https://example.org"
        self.assertNotEqual(self.run_cmd("check-connection", "connection", args).returncode, 0)
        self.assertEqual(server.calls, [])

    def test_redirect_blocked(self):
        server, args = self.start_server()
        server.redirect = True
        self.assertNotEqual(self.run_cmd("check-connection", "connection", args).returncode, 0)
        self.assertEqual(len(server.calls), 1)

    def test_no_confirmation_no_writes(self):
        server, args = self.start_server()
        self.assertNotEqual(self.run_cmd("ingest", "import", args).returncode, 0)
        self.assertEqual(server.calls, [])

    def test_changed_input_no_writes(self):
        server, args = self.start_server()
        self.assertEqual(self.run_cmd("dry-run", "preview").returncode, 0)
        (self.inputs / "note.txt").write_text("Changed synthetic input")
        r = self.run_cmd(
            "ingest",
            "import",
            args
            + [
                "--confirm-ingest",
                "--review-validation",
                str(self.root / "preview/validation.json"),
            ],
        )
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(server.calls, [])

    def test_synthetic_upload_and_partial_failure(self):
        server, args = self.start_server()
        self.assertEqual(self.run_cmd("dry-run", "preview").returncode, 0)
        extra = args + [
            "--confirm-ingest",
            "--review-validation",
            str(self.root / "preview/validation.json"),
        ]
        r = self.run_cmd("ingest", "import", extra)
        self.assertEqual(
            r.returncode, 0, r.stdout + r.stderr + (self.root / "import/import.log").read_text()
        )
        self.assertIn(("POST", "/api/v1/upload-by-id"), server.calls)
        receipt = json.loads((self.root / "import/receipt.json").read_text())
        self.assertEqual(receipt["status"], "COMMAND_SUCCEEDED_RECONCILIATION_REQUIRED")
        server.fail_upload = True
        r = self.run_cmd("ingest", "failed", extra)
        self.assertNotEqual(r.returncode, 0)
        for folder in ("import", "failed"):
            for p in (self.root / folder).iterdir():
                self.assertNotIn(KEY, p.read_text())


if __name__ == "__main__":
    unittest.main()
