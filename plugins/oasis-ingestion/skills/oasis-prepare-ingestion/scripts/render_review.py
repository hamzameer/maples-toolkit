#!/usr/bin/env python3
"""Render a protected inventory review as offline, script-free HTML."""

import argparse
import csv
import hashlib
import html
import io
import json
from collections import Counter
from pathlib import Path

from validate_manifest import FIELDS, validate


def selected_inventory(manifest_path, data_dir):
    report = validate(manifest_path, data_dir)
    if report["status"] != "PASS":
        raise ValueError(
            "selected manifest failed validation; inspect its protected validation report"
        )
    raw = manifest_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != report["manifest_sha256"]:
        raise ValueError("manifest changed during review generation")
    groups = {}
    for row in csv.DictReader(io.StringIO(raw.decode("utf-8"), newline="")):
        row = {k: v.strip() for k, v in row.items()}
        group = tuple(row[k] for k in ("cohort_name", "activity", "case_name"))
        entry = groups.setdefault(group, {"encounters": set(), "counts": Counter()})
        entry["encounters"].add(tuple(row[k] for k in FIELDS[:7]))
        kind = row["file_type"]
        modality = (
            "notes"
            if kind.startswith("notes_")
            else "transcripts"
            if kind.startswith("transcript_")
            else kind
            if kind in ("video", "audio")
            else "other"
        )
        entry["counts"][modality] += 1
        entry["counts"]["files"] += 1
    rows = []
    for key, entry in sorted(groups.items()):
        rows.append(
            list(key)
            + [len(entry["encounters"])]
            + [
                entry["counts"][k]
                for k in ("notes", "transcripts", "video", "audio", "other", "files")
            ]
        )
    return {"rows": rows, "counts": report["counts"], "sha256": report["manifest_sha256"]}


def esc(value):
    return html.escape(str(value), quote=True)


def integer(value):
    return type(value) is int and value >= 0


def render(data, selected=None):
    if data["phase"] not in ("initial", "final"):
        raise ValueError("phase must be initial or final")
    for row in data["inventory"]:
        if not all(integer(row[k]) for k in ("found", "included", "excluded", "unresolved")):
            raise ValueError("inventory counts must be nonnegative integers")
        if row["found"] != sum(row[k] for k in ("included", "excluded", "unresolved")):
            raise ValueError("inventory dispositions must reconcile with found count")
    if len({row["category"] for row in data["inventory"]}) != len(data["inventory"]):
        raise ValueError("inventory categories must be unique")
    for row in data["checks"]:
        if row["status"] not in ("PASS", "FAIL", "NOT_RUN", "BLOCKED"):
            raise ValueError("unsupported check status")
    manifest = data.get("manifest")
    if data["phase"] == "final" and not isinstance(manifest, dict):
        raise ValueError("final review requires manifest counts")
    if manifest is not None and not all(
        integer(manifest[k]) for k in ("rows", "encounters", "learners", "derivatives")
    ):
        raise ValueError("manifest counts must be nonnegative integers")
    if data["phase"] == "final":
        if selected is None:
            raise ValueError("final review requires --manifest and --data-dir")
        for report_key, count_key in (
            ("rows", "files"),
            ("encounters", "encounters"),
            ("learners", "learners"),
        ):
            if manifest[report_key] != selected["counts"][count_key]:
                raise ValueError("reported manifest totals disagree with selected CSV")

    def table(headers, rows):
        return (
            '<div class="table"><table><thead><tr>'
            + "".join('<th scope="col">' + esc(h) + "</th>" for h in headers)
            + "</tr></thead><tbody>"
            + "".join(
                "<tr>" + "".join("<td>" + esc(c) + "</td>" for c in row) + "</tr>" for row in rows
            )
            + "</tbody></table></div>"
        )

    body = (
        "<h1>"
        + esc(data["title"])
        + '</h1><p class="status">'
        + esc(data["phase"].capitalize() + " inventory · " + data["review_status"])
        + "</p><p>"
        + esc(data["summary"])
        + "</p>"
    )
    body += "<h2>Source inventory</h2>" + table(
        ["Category", "Found", "Included", "Excluded", "Unresolved"],
        [
            [r[k] for k in ("category", "found", "included", "excluded", "unresolved")]
            for r in data["inventory"]
        ],
    )
    if manifest is not None:
        body += "<h2>Manifest inventory</h2>" + table(
            ["File rows", "Encounters", "Learners", "Generated derivatives"],
            [[manifest[k] for k in ("rows", "encounters", "learners", "derivatives")]],
        )
    if selected is not None:
        totals = [sum(row[i] for row in selected["rows"]) for i in range(3, 10)]
        body += "<h2>Selected upload inventory</h2><p>Calculated from the reviewed CSV. Encounters are distinct encounter keys; modality columns count files, not learners or encounters. Zero means no file selected, not proof that none was expected.</p>"
        body += table(
            [
                "Cohort",
                "Activity",
                "Case",
                "Encounters",
                "Notes",
                "Transcripts",
                "Videos",
                "Audio",
                "Other",
                "Total files",
            ],
            selected["rows"] + [["All selected", "", ""] + totals],
        )
        body += (
            "<details><summary>Selected manifest SHA-256</summary><pre>"
            + esc(selected["sha256"])
            + "</pre></details>"
        )
    body += "<h2>Mapping understanding</h2>" + table(
        ["Rule", "Evidence", "Decision status"],
        [[r[k] for k in ("rule", "evidence", "status")] for r in data["mapping_rules"]],
    )
    body += "<h2>Questions and unresolved decisions</h2>"
    body += (
        "<ul>" + "".join("<li>" + esc(q) + "</li>" for q in data["questions"]) + "</ul>"
        if data["questions"]
        else "<p>No open questions recorded.</p>"
    )
    body += "<h2>Verification</h2>" + table(
        ["Check", "Status", "Evidence / limits"],
        [[r[k] for k in ("check", "status", "evidence")] for r in data["checks"]],
    )
    body += (
        "<details><summary>Detailed references and hashes</summary><pre>"
        + esc(data.get("details", "No additional details recorded."))
        + "</pre></details><footer>Offline preparation review. This report does not authorize upload or grading.</footer>"
    )
    return (
        """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>"""
        + esc(data["title"])
        + """</title><style>
body{font:16px/1.55 system-ui,sans-serif;color:#172a39;background:#f5f7fa;margin:0}
main{max-width:1060px;margin:36px auto;padding:32px;background:white;border:1px solid #dce3ea;border-radius:12px}
h1{line-height:1.2}h2{font-size:1.15rem;margin-top:30px}.status{color:#34516c;font-weight:600}
.table{overflow-x:auto}table{border-collapse:collapse;width:100%;margin:12px 0}
th,td{text-align:left;vertical-align:top;padding:12px;border-bottom:1px solid #dce3ea;overflow-wrap:anywhere}th{background:#edf2f7}
details{margin:28px 0}summary{cursor:pointer}pre{white-space:pre-wrap;overflow-wrap:anywhere}
footer{border-top:1px solid #dce3ea;padding-top:20px;color:#465a6c;font-size:.9rem}
@media(max-width:700px){main{margin:0;padding:18px;border-radius:0}}
</style></head><body><main>"""
        + body
        + "</main></body></html>\n"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--manifest", type=Path, help="Final selected ingest.csv; required for final review"
    )
    parser.add_argument("--data-dir", type=Path, help="Input root used by the importer")
    args = parser.parse_args()
    try:
        if bool(args.manifest) != bool(args.data_dir):
            raise ValueError("--manifest and --data-dir must be supplied together")
        selected = selected_inventory(args.manifest, args.data_dir) if args.manifest else None
        page = render(json.loads(args.input.read_text(encoding="utf-8")), selected)
        import os

        # Exclusive creation preserves previous receipts; mode restricts output.
        fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(page)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f"Review generation failed: {exc}\n")


if __name__ == "__main__":
    main()
