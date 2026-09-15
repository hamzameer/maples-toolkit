---
name: oasis-prepare-ingestion
description: Inventory data with the user, prepare and review an Elephant import package, configure an existing Elephant connection securely, and offer ingestion after explicit confirmation. Does not deploy Elephant or run grading.
---
# Prepare OASIS ingestion

Produce a reviewable import package from a user-selected data directory.
Use the existing Elephant CSV loader contract; do not infer that a successful
preparation authorizes upload or grading.
These instructions use ordinary filesystem and shell tools and can be followed by Codex
or Claude.

## Establish the boundary

Identify the exact input root, fresh output directory, and permitted operations.
Check for Python 3.10+ before invoking the bundled tools.
If unavailable, follow first-time setup in the portable runtime reference: reuse a
compatible user installation or approved cluster module, or help install a user-local
Python. Explain the installation location and downloads, honor existing authorization,
and avoid changing the system Python.
This prerequisite check does not require an Elephant endpoint or key.
Begin with inventory; do not make a run ID or pre-existing mapping file a prerequisite
to that conversation.
Reuse a supplied run ID; otherwise propose a simple stable label when preparing outputs.
It identifies this preparation, not a server-issued ID. Confirm the intended cohort name
separately. Use existing session authorization; ask only for missing decisions.
Never scan a home directory, shared mount, or another batch to find missing inputs
unless that scope was explicitly selected.
Do not overwrite a prior run or source.

For protected data, confirm both the execution host and the agent/model service are
permitted to receive the information they will observe.
SSH into an approved host does not approve forwarding filenames, identifiers, document
contents, or tool output to a cloud agent.
If that boundary is not approved, prepare code and synthetic examples only; have the
operator run tools locally with detailed output retained in protected storage.
Custody permission does not automatically allow extraction, conversion, linkage, or
analysis. State the exact missing gate when blocked, and continue synthetic work where
useful.

Do not request API keys in chat or print them.
Use secure local entry or an existing approved secret source during connection setup.
No credentials or network access are needed for this skill's validator.
Never invoke model-assisted scanning of protected inputs merely because a provider
happens to be configured.

## Inventory, discuss, then prepare

Read [the CSV contract](references/csv-contract.md) and
[portable runtime](references/portable-runtime.md).
The bundle includes the importer and SDK from `runtime/provenance.json`; use those
together by default.
If a separate OASIS source checkout or installed command is available, verify it against
that checkout's `scripts/load-data.py`, SDK file-type registry, and
`docs/elephant-maples-data-interop.md`; record the revision.
Those product-source paths are not plugin-relative.
Without a separate checkout, use the importer, SDK, and exact source provenance bundled
under `runtime/`. Resolve contract drift before generating real imports.

1. Preserve the as-received package and record its SHA-256 in the protected run record.
   Independent ZIP downloads can differ in container metadata; distinguish archive
   identity from equivalence of uncompressed members.
   Only compare member paths and hashes when intake permission allows it.
   Before extraction reject absolute/traversing names, symlinks, duplicate destination
   paths, and unreasonable expansion.
   Never extract over sources.

2. Inventory only the named root.
   Record file counts by type/folder and the actual member list in a protected
   inventory. Distinguish package containers from their member files to avoid
   double-counting. Preserve this initial snapshot.
   Classify likely evidence, human answer/label files, rubrics, masters, unrelated
   files, and uncertain files.
   Every source member needs a disposition, even when excluded.
   Hash sources at inventory time when permitted; the user need not inspect hash strings
   to discuss the inventory.

3. Present the initial inventory and explain the apparent organization.
   Use filenames, directory structure, file types, embedded metadata, and permitted
   content inspection as evidence for proposed learner/case/block/date mapping.
   A separate mapping workbook is not required.
   Distinguish observed facts from interpretations; cite the source of each rule and any
   contradictions. Batch meaningful questions: for example, whether a filename segment is
   a learner code, whether two folders belong to the same cohort, and whether forms are
   human answers. Do not ask users to reconfirm established facts.

4. Reach and record an understanding with the user about inclusion/exclusion, filename
   conventions, encounter grouping, and missing/conflicting metadata.
   Wait for answers on ambiguous or proposed rules before applying them as final
   mappings; independent inventory and synthetic checks may continue.
   Explicitly supplied rules in the current session already count as confirmed.
   Record who confirmed each decision and when.
   Use existing emails when present and permitted.
   If emails are missing, propose synthetic email-shaped identifiers using the scheme in
   the CSV reference; explain that these are importer identity keys, not verified
   contact addresses. Obtain the user's confirmation of the scheme and its scope before
   applying it, unless already explicitly authorized.
   Persist the mapping, reuse it on retries, and check uniqueness and potential
   collisions with existing server identities.
   An absent email need not block preparation once the synthetic scheme is agreed.
   Do not invent dates, silently deduplicate conflicting records, or equate similar
   codes across packages.
   Unresolved learner identity still blocks assigning synthetic identifiers; an invented
   email cannot resolve who a file belongs to.
   Other missing required fields remain unresolved.
   Confirmation of inventory/mapping does not grant processing or endpoint approval.
   Human labels and completed grading forms must not enter model evidence inputs.
   Protect pseudonymous linkage like other identity mappings.

5. Before writing the final package, ask where the user wants it saved.
   Propose an absolute path on the approved host, explaining which files it will hold.
   Reuse a destination explicitly selected in this session without asking again.
   Confirm a new destination is within the permitted storage boundary; never silently
   choose Downloads, a source repository, or local storage for protected data.
   Create a fresh run directory with the approved permissions, check effective access,
   and preserve earlier reports.
   Explain whether inputs remain referenced in their immutable location or are copied;
   never move or delete originals.
   If the destination changes, regenerate relative paths and rerun validation there.
   Initial inventory/report files also need a permitted location; ask early if none is
   established. Write `ingest.csv` with one row per eligible file and relative file paths
   using the confirmed rules.
   Never present a draft with pending rules as final.
   Reuse the same seven encounter fields for files belonging to one encounter.
   Keep original evidence immutable.
   Any approved conversion produces a new derivative with source/output hashes,
   tool/version, command, and validation of text extraction; do not rename DOCX/PDF
   bytes to TXT. Inspect extraction fidelity locally before declaring those derivatives
   ready.

6. Write the protected run record and QC report: input/output hashes, code revision,
   mapping provenance, expected and observed encounters/files by modality, missingness,
   exclusions, transformations, duplicate dispositions, unresolved decisions, and the
   exact next step/owner.
   Keep human-label denominators distinct from available evidence counts.
   Git/chat gets only permitted, disclosure-reviewed summaries and pointers; never
   assume that counts, hashes, or filenames are automatically safe for publication.

7. Present a final inventory reconciled against the initial snapshot: found, included,
   excluded, and unresolved source members by category; generated derivatives
   separately; resulting manifest rows, encounters, learners, modalities, and missing
   evidence. Each input must have exactly one source disposition.
   Link included originals to manifest paths (possibly through derivatives), explain
   one-to-many conversions, and account for every CSV row.
   Never equate source counts with derivative or encounter counts.
   Flag changes since the initial inventory and return to discussion when they
   invalidate confirmed rules.
   Ask the user to review the final reconciliation, with any open decisions plainly
   visible. Record review status separately from mechanical checks; never manufacture a
   user's acceptance.

Use a fresh owner-restricted run folder (`umask 077` on POSIX), respecting the site's
approved ACL. A suggested layout is `ingest.csv`, `inputs/`, `RUN.md`,
`inventory.initial.json`, `qc.json`, and `checksums.sha256`. Hash derivatives and the
final CSV after generation; recheck source hashes before handoff to detect changes since
inventory. Existing immutable payload files may instead be referenced relative to a
separately selected `--data-dir`; copying is not required.
Do not create symlinks to bypass the selected-root boundary.

## Review presentation

Prefer a self-contained static HTML report when the inventory is large or the user asks
for a visual presentation.
A short inventory can be a Markdown table.
Read [HTML review format](references/html-review.md) for the bundled renderer and its
JSON input.
Generate separately versioned initial and final reports; do not overwrite the
initial snapshot or earlier review decisions.
Use the same inventory/QC facts for HTML and reconciliation, not manually retyped
counts. The report is a view of evidence, not an alternate source of truth.

Keep it simple: summary counts, category reconciliation, proposed/confirmed mapping
rules and evidence, questions, verification results, and final manifest counts.
Put per-file details and hashes behind native expandable sections.
The final HTML must also include a **selected upload inventory**, computed directly from
the final `ingest.csv` via the renderer's `--manifest` and `--data-dir` options.
Group by cohort, activity, and case; show distinct encounters and counts of notes,
transcripts, videos, audio, other files, and total files, with overall totals.
Count multiple files of one modality as multiple files, not extra encounters.
Show zero selected modalities explicitly; expected-but-missing evidence stays in QC.
Reject mismatches with the final summary.
This second inventory describes the selected upload, while the source inventory accounts
for every original file, including exclusions.
Elephant's CSV has no MAPLES group field.
If the user selects named groups, record their explicit membership/selection rules and
resolve them to CSV rows; do not fabricate group labels or imply that this import
creates MAPLES groups.
Overlapping group membership must not duplicate uploaded files or inflate the overall
totals. The CSV-derived cohort/activity/case table remains canonical.
No JavaScript, remote assets, analytics, server, or upload is needed.
Escape all data as text.
No report link should fetch a learner file or send its name to another service.
Keep reports containing protected metadata on approved storage; opening them on a laptop
is a transfer requiring the same scope as the underlying metadata.
Do not use hosted visualization tools for them.
HTML has no approval button: record actual user replies in the run record, then
regenerate a new report version with the recorded decision.

## Validate the saved package

Run the bundled standard-library validator on the approved host:

```bash
python3 <skill-dir>/scripts/validate_manifest.py \
  --csv <run-dir>/ingest.csv --data-dir <input-root> \
  > <run-dir>/manifest-validation.json
```

It checks structure, bounded paths, supported evidence types/extensions, duplicate file
references, basic identity/date shape, and reports hashes and counts.
It is intentionally narrower than the full Elephant file registry.
It does not prove semantic mapping, document readability, endpoint access, server
compatibility, package completeness, or processing clearance.
Keep its report protected; detailed validation errors can contain paths.

After reconciling QC, run the bundled importer's offline preview:

```bash
python3 <skill-dir>/scripts/run_import.py dry-run \
  --csv <run-dir>/ingest.csv --data-dir <input-root> \
  --receipt-dir <run-dir>/preview-v1
```

Alternatively use `oasis data import ... --dry-run` when its loader is installed.
The existing loader's preview prints learner identities and filenames.
Never return that log through an unapproved agent tool channel.
A zero exit code is not enough: reconcile expected counts and skipped rows as well as
errors. The bundled dry run needs no SDK installation or credentials.
If bundle integrity fails, report the blocker rather than fetching an unpinned
substitute.

Report one of: `BLOCKED` (mapping/gates missing), `PREPARED` (files written, checks
incomplete), or `VALIDATED_FOR_REVIEW` (offline checks and QC complete).
None means ingested or graded.
Continue with connection setup and the final ingestion prompt below when that is in the
user's requested workflow.
For retries, use a new receipt and reconcile partial server writes first; never delete
cohorts or overwrite prior review state to obtain a clean run.

## Configure the connection and offer ingestion

Read [connection and ingestion handoff](references/connection-handoff.md).
Here “set up Elephant” means configure access to an existing approved service, not
deploy a server, create keys, change server roles, or install a stack.
Clarify only if the user actually needs a new service.
Before upload, check the private importer environment using
`setup_importer.py --venv <path> --check`. If missing, explain the local installation
and choose a fresh private environment path with the user; run `setup_importer.py` as
described in the runtime reference within existing setup authorization.
It installs locked client dependencies only.
Do not require an OASIS binary or source checkout.
Identify Python, venv/uv, network, platform-wheel, or site-policy blockers.
Offer guided user-local Python setup when missing; do not change system packages or the
system Python.

After the final package review and before connection checks, ask the user to point to a
private dotfile on the execution host containing `ELEPHANT_API_KEY` and
`ELEPHANT_API_URL`. Reuse that path if already supplied.
If no file exists, guide the user to populate one through secure local entry, outside
chat. Use `run_import.py` to parse the private file locally, check the exact reviewed
URL, and pass these native configuration names directly to the importer.
Keep the dotfile in a private location outside the run package and repositories.
Do not read secrets back into tool output.
Verify the intended target and available read-only access; distinguish health,
authentication, authorization, and cohort isolation.
Do not test write permission by creating or uploading anything before ingestion
confirmation.

Finish all authorized preparation and read-only checks first, then present the saved
location, reviewed counts/exclusions, exact endpoint/cohort, manifest hash, check
results, and any limitations.
Ask: “Ingest this reviewed manifest into this Elephant target now?”
unless explicit approval already covers these exact bytes and target.
The user requested this final prompt; inventory confirmation or credential entry alone
is not ingestion consent.
If blocked, explain the specific blocker instead of offering a runnable go/no-go.
Wait for the answer.
After approval, use the bundled `run_import.py ingest` with the reviewed validation
receipt and `--confirm-ingest` to execute the exact reviewed import once, keep detailed
logs protected, reconcile server results, and report success or partial failure
honestly. A changed manifest, target, or scope needs renewed review.
No automatic grading, sync, cleanup, or retry follows ingestion.

## Design tradeoff

Compass questions 2, 4, 5, and 9 guide this skill: reduce manual preparation without
fabricating metadata or hiding provider exposure.
Explicit CSVs and deterministic validation remain usable without an agent.
The cost is that ambiguous identity and eligibility decisions stay with the data owner
rather than being guessed to make a package appear complete.
