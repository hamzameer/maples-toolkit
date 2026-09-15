#!/usr/bin/env python3
"""Compatibility wrapper for installable plugin smoke tests."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = REPO_ROOT / "plugins" / "rubric-maker-skill"
OASIS_PLUGIN_ROOT = REPO_ROOT / "plugins" / "oasis-ingestion"


def main() -> int:
    checks = (
        (PLUGIN_ROOT, PLUGIN_ROOT / "scripts" / "smoke_test.py"),
        (OASIS_PLUGIN_ROOT, OASIS_PLUGIN_ROOT / "scripts" / "smoke_test.py"),
    )
    for plugin_root, script in checks:
        result = subprocess.run([sys.executable, str(script)], cwd=plugin_root, check=False)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
