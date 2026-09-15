# Static inventory review

Render on the approved host.
For initial reviews the renderer reads only the supplied JSON. For final reviews it also
validates and hashes the explicitly selected manifest/files.
It does not scan unrelated directories or connect to Elephant.
JSON/HTML may still contain protected paths, counts, or mapping details; keep both in
the approved run directory.
Keep content excerpts out of the review by default.

```bash
python3 <skill-dir>/scripts/render_review.py \
  --input <run-dir>/review.initial.v1.json \
  --output <run-dir>/review.initial.v1.html
```

Use `phase: final` for the final reconciliation.
Output creation is exclusive: use a new versioned filename rather than overwrite a prior
report. The JSON is a presentation projection of the recorded inventory/QC, not a
substitute for the complete source-member disposition ledger.

For final review, supply the actual selected manifest and input root:

```bash
python3 <skill-dir>/scripts/render_review.py \
  --input <run-dir>/review.final.v1.json \
  --manifest <run-dir>/ingest.csv --data-dir <input-root> \
  --output <run-dir>/review.final.v1.html
```

The renderer validates the CSV/files, checks that the JSON's manifest totals match it,
and derives a second inventory grouped by cohort, activity, and case.
Columns count distinct encounter keys, note files, transcript files, videos, audio
files, other files, and all files.
It shows the manifest hash and overall totals.
This is selected-to-upload inventory, not proof of server ingestion.
Final reports without the CSV/input-root pair are rejected.
File hashes and mechanical validation do not prove semantic mapping or content
readability. Named MAPLES groups are not a CSV field; resolve explicit group selections
to CSV membership and explain their selection in the review summary rather than
inventing group identities.
Do not duplicate rows for overlapping selections.

Required shape (synthetic example):

```json
{
  "title": "Synthetic ingestion review",
  "phase": "initial",
  "review_status": "Awaiting discussion",
  "summary": "One transcript and one note appear to belong to one encounter.",
  "inventory": [
    {"category": "Transcripts", "found": 1, "included": 0, "excluded": 0, "unresolved": 1},
    {"category": "Notes", "found": 1, "included": 0, "excluded": 0, "unresolved": 1}
  ],
  "mapping_rules": [
    {"rule": "Match files by the demo-001 stem", "evidence": "Both filenames share that stem", "status": "Proposed"}
  ],
  "questions": ["Do these files represent the same encounter?"],
  "checks": [
    {"check": "File inventory", "status": "PASS", "evidence": "Two source files recorded"},
    {"check": "OASIS dry run", "status": "NOT_RUN", "evidence": "Mapping discussion pending"}
  ],
  "manifest": null,
  "details": "Protected per-file disposition ledger: inventory.initial.json"
}
```

For final reports, `manifest` must be an object with nonnegative integer `rows`,
`encounters`, `learners`, and `derivatives`. These are separate units; for one original
converted to multiple evidence files, manifest rows can exceed included original files.
The ledger must explain those relationships.
`found = included + excluded + unresolved` must hold for each category in both phases.
Initial uncertain files remain unresolved, not silently excluded.
Categories must be non-overlapping.
Missing expected files are described in questions/QC, not counted as physically found
members.

Check statuses are `PASS`, `FAIL`, `NOT_RUN`, or `BLOCKED`. Use evidence strings to
distinguish exact comparisons, sampled inspection, and user confirmation.
Never call sampled review exhaustive.
Mechanical PASS does not clear pending questions or imply user approval; `review_status`
records the actual state.
The renderer validates count arithmetic but cannot verify that counts came from files or
that someone approved a rule.
The orchestrating agent must derive report data from the inventory and preserve decision
evidence.
