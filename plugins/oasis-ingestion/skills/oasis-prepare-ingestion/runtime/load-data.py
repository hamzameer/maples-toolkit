#!/usr/bin/env python3
"""
load-data.py -- Generic CSV-driven data loader for Elephant.

Reads a CSV manifest describing encounters and their associated files,
then creates cohorts, learners, encounters, and uploads files via the
Elephant SDK. Idempotent: safe to re-run (upserts cohorts/learners,
reuses encounters, skips duplicate files).

CSV format (one row per file):
  cohort_name,learner_name,learner_email,activity,case_name,date,room,file_path,file_type

  Rows sharing the same (cohort_name, learner_name, learner_email,
  activity, case_name, date, room) are grouped into a single encounter.
  Each encounter can have multiple files.

Usage:
  python load-data.py --csv manifest.csv --data-dir ./sample-data/
  python load-data.py --csv manifest.csv --data-dir ./data/ --dry-run
  ELEPHANT_API_URL=http://localhost:8080 python load-data.py --csv manifest.csv --data-dir ./data/

Load ELEPHANT_API_KEY from a secret manager or hidden shell prompt before a
non-dry-run invocation. Do not paste a literal key into a command.

Environment variables (used when flags are not provided):
  ELEPHANT_API_URL   Base URL of the Elephant API  (default: http://localhost:8080)
  ELEPHANT_API_KEY   API key for authentication
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import NamedTuple

_NO_COLOR = not sys.stdout.isatty() or os.environ.get("NO_COLOR")
def _c(code: str, t: str) -> str: return t if _NO_COLOR else f"\033[{code}m{t}\033[0m"
def green(t: str) -> str: return _c("32", t)
def yellow(t: str) -> str: return _c("33", t)
def red(t: str) -> str: return _c("31", t)
def bold(t: str) -> str: return _c("1", t)
def cyan(t: str) -> str: return _c("36", t)

ENCOUNTER_COLS = ("cohort_name", "learner_name", "learner_email",
                  "activity", "case_name", "date", "room")

class FileRow(NamedTuple):
    file_path: str
    file_type: str

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Load encounter data into Elephant from a CSV manifest.")
    p.add_argument("--csv", required=True, help="Path to the CSV manifest file")
    p.add_argument("--data-dir", required=True, help="Base directory for file_path entries in CSV")
    p.add_argument("--base-url", default=os.environ.get("ELEPHANT_API_URL", "http://localhost:8080"))
    p.add_argument("--api-key", default=os.environ.get("ELEPHANT_API_KEY", ""))
    p.add_argument("--dry-run", action="store_true", help="Show what would happen without making API calls")
    return p.parse_args()

def read_manifest(csv_path: str) -> dict[tuple, list[FileRow]]:
    """Read CSV and group rows by encounter key -> {key: [FileRow, ...]}."""
    encounters: dict[tuple, list[FileRow]] = defaultdict(list)
    with open(csv_path, newline="") as f:
        # Filter out comment lines (starting with #) before passing to DictReader
        lines = [line for line in f if not line.lstrip().startswith("#")]
    import io
    reader = csv.DictReader(io.StringIO("".join(lines)))
    if True:
        if not reader.fieldnames:
            sys.exit(red("ERROR: CSV is empty or has no header"))
        missing = [c for c in list(ENCOUNTER_COLS) + ["file_path", "file_type"] if c not in reader.fieldnames]
        if missing:
            sys.exit(red(f"ERROR: CSV missing columns: {missing}"))
        for i, row in enumerate(reader, start=2):
            key = tuple(row[c].strip() for c in ENCOUNTER_COLS)
            fp, ft = row["file_path"].strip(), row["file_type"].strip()
            if not fp or not ft:
                print(yellow(f"  WARN row {i}: empty file_path/file_type, skipping"))
                continue
            encounters[key].append(FileRow(fp, ft))
    return dict(encounters)

def main() -> None:
    args = parse_args()
    data_dir = Path(args.data_dir).resolve()
    csv_path = Path(args.csv).resolve()

    if not csv_path.exists():
        sys.exit(red(f"ERROR: CSV not found: {csv_path}"))
    if not data_dir.exists():
        sys.exit(red(f"ERROR: data-dir not found: {data_dir}"))

    encounters = read_manifest(str(csv_path))
    total_files = sum(len(files) for files in encounters.values())
    print(bold(f"\n{'DRY RUN -- ' if args.dry_run else ''}Manifest loaded: "
               f"{len(encounters)} encounters, {total_files} files\n"))

    # Pre-flight: verify every referenced file exists on disk
    missing = [str(data_dir / fr.file_path)
               for files in encounters.values() for fr in files
               if not (data_dir / fr.file_path).exists()]
    if missing:
        for mf in missing[:10]:
            print(red(f"  MISSING: {mf}"))
        if len(missing) > 10:
            print(red(f"  ... and {len(missing) - 10} more"))
        sys.exit(red(f"\nERROR: {len(missing)} file(s) not found. Fix paths and re-run."))

    if args.dry_run:
        _dry_run_report(encounters, data_dir)
        return

    if not args.api_key:
        sys.exit(red("ERROR: --api-key or ELEPHANT_API_KEY required (not in dry-run mode)"))
    try:
        from elephant import ElephantClient, FileToUpload, ElephantError, ElephantHTTPError
    except ImportError:
        sys.exit(red("ERROR: elephant SDK not installed. pip install -e /path/to/elephant-sdk"))

    client = ElephantClient(api_key=args.api_key, base_url=args.base_url)

    try:
        client.get_health()
        print(green("  API health check passed"))
    except Exception as e:
        sys.exit(red(f"ERROR: health check failed: {e}"))

    cohorts_created = cohorts_reused = 0
    learners_created = learners_reused = 0
    encounters_created = encounters_reused = 0
    files_uploaded = files_duplicate = files_failed = 0

    cohort_learners: dict[str, dict[str, str]] = defaultdict(dict)
    for key in encounters:
        cohort_learners[key[0]][key[2]] = key[1]  # {cohort: {email: name}}

    print(bold("\n-- Step 1: Upsert learners, then link cohorts --"))
    # epub-v2 contract: /learners/bulk creates/updates learners; /cohorts then
    # links EXISTING learners by email (per-email link outcomes).
    for cohort_name, learner_map in cohort_learners.items():
        items = [{"learner_name": n, "email": e} for e, n in learner_map.items()]
        try:
            bulk = client.upsert_learners_bulk(items=items)
            for lr in bulk.results:
                le = getattr(lr, "learner_entry", "reused")
                if str(le).endswith("created"):
                    learners_created += 1
                else:
                    learners_reused += 1
            resp = client.upsert_cohort(
                cohort_name=cohort_name,
                learner_emails=list(learner_map.keys()),
            )
            ce = getattr(resp, "cohort_entry", "reused")
            if str(ce).endswith("created"):
                cohorts_created += 1
                print(green(f"  + Cohort CREATED: {cohort_name}"))
            else:
                cohorts_reused += 1
                print(cyan(f"  = Cohort reused:  {cohort_name}"))
        except ElephantError as e:
            print(red(f"  ! Cohort FAILED: {cohort_name} -- {e}"))

    print(bold("\n-- Step 2: Create encounters & upload files --"))
    for key, files in encounters.items():
        cohort, name, email, activity, case, date_str, room = key
        try:
            enc = client.create_encounter(
                case_name=case,
                activity_name=activity,
                date=date_str,
                cohort_name=cohort,
                learner_emails=[email],
                room=room or None,
            )
            ee = getattr(enc, "encounter_entry", "reused")
            eid = enc.encounter_id
            if ee == "created":
                encounters_created += 1
                print(green(f"  + Encounter CREATED: {case} / {activity} / {name}"))
            else:
                encounters_reused += 1
                print(cyan(f"  = Encounter reused:  {case} / {activity} / {name}"))
        except ElephantError as e:
            print(red(f"  ! Encounter FAILED: {case}/{activity}/{name} -- {e}"))
            files_failed += len(files)
            continue

        # Upload files for this encounter
        for fr in files:
            full_path = data_dir / fr.file_path
            try:
                result = client.upload_file_by_id(
                    encounter_id=eid,
                    file_path=str(full_path),
                    file_type=fr.file_type,
                )
                if result.status == 201:
                    files_uploaded += 1
                    print(green(f"    + Uploaded: {fr.file_path}"))
                elif result.status == 200:
                    files_duplicate += 1
                    print(yellow(f"    ~ Duplicate (skipped): {fr.file_path}"))
                else:
                    files_uploaded += 1
                    print(green(f"    + Uploaded ({result.status}): {fr.file_path}"))
            except ElephantHTTPError as e:
                if e.status == 409:
                    files_duplicate += 1
                    print(yellow(f"    ~ Duplicate (skipped): {fr.file_path}"))
                else:
                    files_failed += 1
                    print(red(f"    ! FAILED: {fr.file_path} -- {e}"))
            except ElephantError as e:
                files_failed += 1
                print(red(f"    ! FAILED: {fr.file_path} -- {e}"))

    print(bold("\n========== Summary =========="))
    print(f"  Cohorts:     {green(str(cohorts_created) + ' created')}, {cyan(str(cohorts_reused) + ' reused')}")
    print(f"  Learners:    {green(str(learners_created) + ' created')}, {cyan(str(learners_reused) + ' reused')}")
    print(f"  Encounters:  {green(str(encounters_created) + ' created')}, {cyan(str(encounters_reused) + ' reused')}")
    print(f"  Files:       {green(str(files_uploaded) + ' uploaded')}, "
          f"{yellow(str(files_duplicate) + ' duplicates')}, "
          f"{red(str(files_failed) + ' failed')}")
    if files_failed:
        print(red(f"\n  {files_failed} file(s) failed. Review errors above."))
        sys.exit(1)
    print(green("\n  Done.\n"))


def _dry_run_report(encounters: dict[tuple, list[FileRow]], data_dir: Path) -> None:
    """Print what *would* happen without making API calls."""
    cohorts: dict[str, set[str]] = defaultdict(set)
    for key in encounters:
        cohorts[key[0]].add(f"{key[1]} <{key[2]}>")

    print(bold("Cohorts to upsert:"))
    for c, ls in cohorts.items():
        print(f"  {c}")
        for l in sorted(ls):
            print(f"    - {l}")

    print(bold("\nEncounters to create:"))
    for key, files in encounters.items():
        _, name, email, activity, case, date_str, room = key
        label = f"{case} / {activity} / {name}"
        if room:
            label += f" [{room}]"
        print(f"  {label}  ({date_str})")
        for fr in files:
            full = data_dir / fr.file_path
            sz = full.stat().st_size
            print(f"    -> {fr.file_path}  [{fr.file_type}]  ({sz:,} bytes)")

    total = sum(len(f) for f in encounters.values())
    print(bold(f"\nTotals: {len(cohorts)} cohorts, {len(encounters)} encounters, {total} files"))
    print(yellow("  (dry run -- no API calls made)\n"))


if __name__ == "__main__":
    main()
