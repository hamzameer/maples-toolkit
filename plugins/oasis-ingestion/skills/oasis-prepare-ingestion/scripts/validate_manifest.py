#!/usr/bin/env python3
"""Offline evidence-manifest checks. Reports may contain protected paths."""

import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path, PurePosixPath

FIELDS = "cohort_name learner_name learner_email activity case_name date room file_path file_type".split()
TYPES = {
    "transcript_srt": {".srt"},
    "transcript_vtt": {".vtt"},
    "transcript_txt": {".txt"},
    "notes_txt": {".txt"},
    "notes_md": {".md"},
    "notes_json": {".json"},
    "audio": {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac"},
    "video": {".mp4", ".mov", ".mkv", ".webm", ".avi"},
}


def validate(manifest, root):
    errors, files = [], []
    encounters, learners, cohorts, seen = set(), set(), set(), set()
    counts = Counter()
    identity_names = {}
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("data-dir must be a directory")
    raw = manifest.read_bytes()
    manifest_hash = hashlib.sha256(raw).hexdigest()
    # Read the exact bytes that were hashed, with strict CSV parsing.
    import io

    reader = csv.DictReader(io.StringIO(raw.decode("utf-8"), newline=""), strict=True)
    if reader.fieldnames != FIELDS:
        return {"status": "FAIL", "errors": ["Header must match canonical nine-column schema"]}
    for line, row in enumerate(reader, 2):
        label = f"row {line}"
        before = len(errors)
        if None in row or any(v is None for v in row.values()):
            errors.append(f"{label}: wrong number of columns")
            continue
        row = {k: v.strip() for k, v in row.items()}
        for key, value in row.items():
            if key != "room" and not value:
                errors.append(f"{label}: empty {key}")
            if any(ord(c) < 32 for c in value):
                errors.append(f"{label}: control character in {key}")
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", row["learner_email"]):
            errors.append(f"{label}: invalid basic email shape")
        valid_date = False
        for fmt in ("%m/%d/%Y", "%m/%d/%Y %I:%M %p"):
            try:
                datetime.strptime(row["date"], fmt)
                valid_date = True
                break
            except ValueError:
                pass
        if not valid_date:
            errors.append(f"{label}: unsupported or invalid date")
        email = row["learner_email"].casefold()
        if email in identity_names and identity_names[email] != row["learner_name"]:
            errors.append(f"{label}: conflicting names for one email identity")
        identity_names[email] = row["learner_name"]
        rel = PurePosixPath(row["file_path"])
        if (
            rel.is_absolute()
            or ".." in rel.parts
            or "\\" in str(rel)
            or ":" in str(rel)
            or not rel.parts
        ):
            errors.append(f"{label}: path must be relative and bounded")
            continue
        path = root
        for part in rel.parts:
            path = path / part
            if path.is_symlink():
                errors.append(f"{label}: symlinks are not permitted")
                break
        if len(errors) > before:
            continue
        resolved = path.resolve()
        if not resolved.is_relative_to(root) or not resolved.is_file():
            errors.append(f"{label}: missing file or outside input root")
            continue
        if resolved in seen:
            errors.append(f"{label}: duplicate file reference")
        seen.add(resolved)
        kind = row["file_type"]
        if kind not in TYPES or path.suffix.lower() not in TYPES[kind]:
            errors.append(f"{label}: unsupported evidence type/extension combination")
        if len(errors) > before:
            continue
        digest = hashlib.sha256()
        size = 0
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                size += len(chunk)
                digest.update(chunk)
        if size == 0:
            errors.append(f"{label}: empty file")
            continue
        files.append(
            {"path": str(rel), "sha256": digest.hexdigest(), "bytes": size, "file_type": kind}
        )
        encounters.add(tuple(row[k] for k in FIELDS[:7]))
        learners.add(email)
        cohorts.add(row["cohort_name"])
        counts[kind] += 1
    if not files:
        errors.append("No valid evidence files")
    return {
        "status": "FAIL" if errors else "PASS",
        "errors": errors,
        "manifest_sha256": manifest_hash,
        "counts": {
            "cohorts": len(cohorts),
            "learners": len(learners),
            "encounters": len(encounters),
            "files": len(files),
            "by_type": dict(counts),
        },
        "files": files,
        "limits": [
            "No semantic mapping or document readability verification",
            "No completeness, clearance, or endpoint verification",
            "Use immutable inputs; recheck hashes before import",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--data-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        report = validate(args.csv, args.data_dir)
    except (OSError, UnicodeError, ValueError, csv.Error) as exc:
        report = {"status": "FAIL", "errors": [str(exc)]}
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
