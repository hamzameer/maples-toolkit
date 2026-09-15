#!/usr/bin/env python3
"""Run self-contained smoke checks for the OASIS ingestion plugin."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
SKILL_ROOT = PLUGIN_ROOT / "skills" / "oasis-prepare-ingestion"
REPO_ROOT = PLUGIN_ROOT.parent.parent


def run(command: list[str], *, cwd: Path = REPO_ROOT) -> None:
    result = subprocess.run(command, cwd=cwd, check=False)
    if result.returncode:
        raise SystemExit(result.returncode)


def check_manifest() -> None:
    payload = json.loads(
        (PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    if payload.get("name") != "oasis-ingestion" or payload.get("skills") != "./skills/":
        raise SystemExit("OASIS ingestion plugin manifest is not discoverable")


def main() -> int:
    check_manifest()
    run(
        [
            sys.executable,
            str(SKILL_ROOT / "tests" / "test_portable_runtime.py"),
        ]
    )

    with tempfile.TemporaryDirectory(prefix="oasis-ingestion-smoke-") as temp:
        root = Path(temp)
        data = root / "data"
        data.mkdir()
        (data / "note.txt").write_text("synthetic note\n", encoding="utf-8")
        manifest = root / "ingest.csv"
        manifest.write_text(
            "cohort_name,learner_name,learner_email,activity,case_name,date,room,file_path,file_type\n"
            "SYNTHETIC,Demo Learner,demo@example.org,Demo OSCE,Demo Case,09/15/2026,,note.txt,notes_txt\n",
            encoding="utf-8",
        )
        validation = root / "validation.json"
        with validation.open("w", encoding="utf-8") as output:
            result = subprocess.run(
                [
                    sys.executable,
                    str(SKILL_ROOT / "scripts" / "validate_manifest.py"),
                    "--csv",
                    str(manifest),
                    "--data-dir",
                    str(data),
                ],
                stdout=output,
                check=False,
            )
        if result.returncode:
            raise SystemExit(result.returncode)
        if json.loads(validation.read_text(encoding="utf-8"))["status"] != "PASS":
            raise SystemExit("synthetic manifest validation did not pass")

    print("PASS OASIS ingestion plugin smoke checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
