# Elephant evidence import contract

Required headers, in canonical order:

```csv
cohort_name,learner_name,learner_email,activity,case_name,date,room,file_path,file_type
```

Write UTF-8 without BOM using a CSV writer; quote embedded commas.
The loader strips surrounding field whitespace.
Keep fields single-line and do not use comment lines.
All headers are required; `room` may be empty.
Other fields must be explicit.
The validator accepts dates as `MM/DD/YYYY` or `MM/DD/YYYY HH:MM AM/PM`; this
preparation profile is narrower than the server.
Never insert a fictitious encounter date just to satisfy it.

## Missing email addresses

Use supplied real emails when present and their use is permitted.
If absent, propose clearly synthetic importer identifiers and confirm the scheme with
the user before filling the manifest.
For example:

```text
synthetic-<namespace>-000001@example.org
synthetic-<namespace>-000002@example.org
```

`example.org` is a reserved example domain; these are identity keys, not contact
addresses. Never use a guessed address at a real institution's domain or send mail to
these identifiers. Verify syntax against the bundled SDK and the selected server's
applicable policy. Do not substitute `.invalid` without checking SDK acceptance; the
SDK's email validator can reject special domains.

Use an opaque, collision-resistant namespace, for example an owner-confirmed random
hexadecimal batch namespace, and a persisted learner-to-email mapping.
Assign one identifier per resolved learner and reuse it across that learner's encounters
and modalities within the agreed scope.
Do not derive the ordinal from a changing file sort or assign one email per file.
Retain the mapping on reruns.
Across new batches, reuse existing learner identity only when the owner confirms that
linkage is intended; new namespaces can otherwise create new server learner records.
Check case-insensitive uniqueness within the package and existing target identities when
authorized. Review collisions instead of silently updating or merging a learner.
Label the mapping's origin as synthetic and record the user's confirmation, scope, and
date in QC and the final review.
Keep the mapping protected: synthetic emails can still be linkable identifiers.
If learner identity itself is ambiguous, resolve it before generating emails.

One row is one file.
The first seven fields together form the loader's encounter grouping key.
Paths are relative to `--data-dir`, which need not be the current directory.
Use `/`, not Windows backslashes.
Subdirectory names do not control mappings.
No absolute paths, `..`, symlinks, or duplicate file references.
A missing note is QC missingness, not a path to a nonexistent file.

Evidence profile supported by the bundled validator:

| File type | Extension |
| --- | --- |
| `transcript_srt` | `.srt` |
| `transcript_vtt` | `.vtt` |
| `transcript_txt` | `.txt` |
| `notes_txt` | `.txt` |
| `notes_md` | `.md` |
| `notes_json` | `.json` |
| `audio` | `.wav`, `.mp3`, `.m4a`, `.flac`, `.ogg`, `.aac` |
| `video` | `.mp4`, `.mov`, `.mkv`, `.webm`, `.avi` |

Audio/video require their own approved modality scope.
Other server-supported types require an explicit profile extension and validation; do
not label them as a supported type to pass.
In particular, the inspected SDK has no `notes_docx` type.
Any DOCX-to-text conversion is a governed derivative, not just an extension change.
JSON notes require semantic review beyond JSON syntax.

Synthetic example (never substitute these identities/dates for real ones):

```text
run/
  ingest.csv
  inputs/
    transcripts/demo-001.srt
    notes/demo-001.txt
```

```csv
cohort_name,learner_name,learner_email,activity,case_name,date,room,file_path,file_type
SYNTHETIC-DEMO,Demo Learner,demo001@example.org,Demo OSCE,Demo Case,09/10/2026 09:00 AM,Demo Room,transcripts/demo-001.srt,transcript_srt
SYNTHETIC-DEMO,Demo Learner,demo001@example.org,Demo OSCE,Demo Case,09/10/2026 09:00 AM,Demo Room,notes/demo-001.txt,notes_txt
```

Expected result: one cohort, one learner, one encounter, two files.
Human forms, rubric spreadsheets, and answer keys stay out of this evidence manifest.

The OASIS CLI delegates to the Python loader.
A source checkout needs Python 3.10+ and `elephant-sdk` for live import; the loader's
dry run requires no SDK or credentials.
Live import needs an approved Elephant URL and `read_write` key supplied through
environment/managed configuration, never literal command arguments or logs.
Preparing a manifest does not establish that access.
