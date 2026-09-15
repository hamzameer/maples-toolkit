# OASIS Ingestion

This plugin packages the `oasis-prepare-ingestion` skill and its deterministic helpers
for Codex CLI and Claude Code.
It prepares a reviewable Elephant CSV import from a user-selected data package,
validates it offline, configures a private client runtime, and offers a guarded one-time
import after the user confirms the exact manifest and target.

It does not deploy Elephant, grant data-processing clearance, grade evidence, or infer
that inventory review authorizes upload.

## Install

Add this repository as a marketplace once, then install the plugin.

### Codex CLI

```bash
codex plugin marketplace add https://github.com/JamiesonLabUTSW/maples-toolkit
codex plugin add oasis-ingestion@ut-real-project-maples
```

### Claude Code

```bash
claude plugin marketplace add https://github.com/JamiesonLabUTSW/maples-toolkit
claude plugin install oasis-ingestion@ut-real-project-maples
```

For local development:

```bash
claude --plugin-dir plugins/oasis-ingestion
```

Invoke the installed skill as `$oasis-prepare-ingestion` and identify the exact input
root.
The skill begins with custody and disclosure boundaries before inspecting protected
data.

## Bundled surfaces

- `skills/oasis-prepare-ingestion/SKILL.md`: the agent workflow and authorization
  boundaries.
- `references/`: CSV, review-report, portable-runtime, and connection contracts.
- `scripts/validate_manifest.py`: standard-library offline manifest validation.
- `scripts/render_review.py`: script-free HTML inventory and selected-upload reports.
- `scripts/setup_importer.py`: a private, hash-locked Python client environment.
- `scripts/run_import.py`: guarded dry-run, connection-check, and confirmed-import
  receipts.
- `runtime/`: an unchanged OASIS CSV importer, Elephant SDK wheel, frozen dependency
  hashes, source licenses, integrity inventory, and exact source provenance.

The runtime provenance pins the importer and SDK to OASIS commit
`701e1a6210aeda51af1ebfb94148d28cf2843c5e`. It is a private engineering client bundle,
not an OASIS release or Elephant server installer.
The dependency setup uses the public package index for hash-locked binary wheels; it is
not fully offline. References in the skill to `scripts/load-data.py` and
`docs/elephant-maples-data-interop.md` mean paths in an optional, separate OASIS source
checkout. The plugin's default importer is the provenance-pinned copy under
`skills/oasis-prepare-ingestion/runtime/`; no OASIS checkout is required.

## Prerequisites and security boundary

Preparation and dry-run require Python 3.10 or newer.
Live connection setup additionally requires a user-private environment and a
user-selected dotenv file containing `ELEPHANT_API_URL` and `ELEPHANT_API_KEY`. Never
put credentials, learner data, raw transcripts, protected filenames, or detailed import
logs in Git, chat, issue bodies, or pull requests.

Before protected inputs are inspected, the operator must confirm both the execution host
and the agent/model-service disclosure boundary.
The skill keeps mapping decisions with the data owner, excludes human grading forms from
model evidence, preserves original bytes, and requires a final confirmation for the
exact reviewed manifest and target.

## Validation and maintenance

Run the plugin smoke test from the repository root:

```bash
python3 plugins/oasis-ingestion/scripts/smoke_test.py
```

The smoke test validates the skill structure, checks bundle integrity, exercises the
offline validator and renderer with synthetic data, and runs the portable runtime tests.
Refresh the importer, SDK wheel, lock, provenance, and integrity inventory together from
an explicitly selected OASIS revision.
Do not edit one vendored runtime component in isolation.

See the skill's
[`references/portable-runtime.md`](skills/oasis-prepare-ingestion/references/portable-runtime.md)
for setup and execution details.
