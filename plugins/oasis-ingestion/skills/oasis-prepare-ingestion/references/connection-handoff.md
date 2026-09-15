# Connection setup and ingestion handoff

## Save the work

Ask the user for the final absolute directory on the approved host before materializing
the final package. Offer a sensible run subdirectory under the selected storage root.
Reuse an already explicit destination.
Keep reports, CSV, QC, and import receipts together; preserve the immutable input
package. Check ownership/effective ACLs, not just `test -w`. Do not change a shared
parent's permissions to accommodate the run.
Store no API key in this package.

## Configure an existing Elephant service

Use the bundled [portable runtime](portable-runtime.md) for setup, private dotfile
parsing, offline preview, connection check, and confirmed import.
An OASIS checkout or binary is optional.
Follow the exact commands and current verification limits in that reference.

Confirm the exact base URL and role of the destination (synthetic test, isolated partner
run, historical read-only replica, or production).
A cohort name is an organizational label, not proof of a security isolation boundary.
Use a fresh approved cohort/namespace and check existing membership before upserting:
the loader can update globally identified learners and reused cohorts.
Do not treat a new cohort name as permission to modify existing data.

After reviewing the final package, ask: “Which private dotfile on the execution host
contains your ELEPHANT_API_KEY and ELEPHANT_API_URL?” Ask for the path only, never its
contents. Reuse a path already provided.
If none exists, propose a target-specific location such as
`~/.config/oasis/connections/.<target>.env` on the execution host, with a `0700`
directory and `0600` regular file owned by the operator.
This is a suggested private config location, not an automatically discovered OASIS path.
Honor site ACL/secret-storage policy.
Check for symlinks and existing files; do not overwrite a connection or broaden access
without discussing the change.

The requested dotfile contract is:

```dotenv
ELEPHANT_API_KEY=
ELEPHANT_API_URL=
```

These blank entries are a template, not a working connection.
Have the user fill them locally.
Parse the file on the execution host without printing it; reject missing, blank, or
duplicate required fields.
Use a dotenv parser compatible with the stored format and do not expand shell commands
or variables. Never `source` an untrusted dotenv file as executable shell code.

Both names match the native OASIS/Elephant loader configuration; no variable renaming is
needed.
For OASIS CLI, explicitly select the file through `OASIS_ENV_FILE` after checking
installed-version support.
For the direct Python loader, securely parse the selected file and pass
`ELEPHANT_API_URL` and `ELEPHANT_API_KEY` through the child environment; it does not
load `OASIS_ENV_FILE` or an arbitrary `.env` automatically.
Reject conflicting ambient/configured URLs or explicitly isolate them so an unrelated
target cannot win. Verify the actual selected endpoint before any authenticated probe.
Never fall back to localhost or another target when `ELEPHANT_API_URL` is absent.
Reuse an existing managed secret mechanism if the user explicitly requests it instead of
this dotfile workflow.

Have the operator enter the key through an approved secret manager or a non-echoing
local terminal prompt outside the agent transcript.
Do not ask them to paste it into chat, put it in command arguments, or put a literal key
in shell history. Do not echo the key or show the env file, process environment, HTTP
auth headers, or debug traces.
Disable shell tracing during secret entry and use safe serialization, not shell string
interpolation. The key can also remain session-only if the user prefers not to save it.
If no safe entry mechanism is available, leave credential setup pending and give
operator instructions; do not collect the secret through a chat tool.

Use TLS or a documented protected loopback tunnel; do not disable certificate
verification or send credentials to an unverified endpoint/redirect.
Read-only probes should return only necessary status and protected inventory summaries.
Health success alone proves neither authentication nor `read_write` role.
Verify role through an existing supported identity/permission interface or
owner-provided credential record.
If unavailable, label it unverified; do not invent an endpoint or create a test object
to prove writes. Resolve permission requirements before presenting the package as ready
to ingest.

## Final user decision

Present this concrete review packet:

- Execution host, saved run directory, and immutable loader/client revision.
- Exact Elephant base URL, destination cohort/namespace, and credential role
  verification status.
  Show only the config path/source, never its contents.
- Manifest hash, encounters, file rows by modality, exclusions, missingness, duplicate
  dispositions, and any existing target objects that could be updated.
- Source/derivative hash recheck, validator and importer dry-run results, user
  mapping/reconciliation review status, and applicable processing clearance.
- Exact import command with paths/config references and a fresh protected log location.
  Explain that it creates/upserts learners, cohorts, encounters, and uploads files; it
  does not grade.

Ask whether to ingest now.
Do not require repeat confirmation if explicit existing approval covers this exact
package/target/action; a generic request to prepare data or set up credentials does not.
Recheck that reviewed bytes and target configuration have not changed immediately before
the approved run.

On execution, supply credentials through the environment, run the existing loader once,
record start/end and exit status, and inspect the protected summary for failed or
skipped items. Independently reconcile target encounter and file inventory with expected
counts/types and available server hashes or identities.
Counts alone cannot prove byte equivalence; record what was and was not checked.
Before/after observations should also detect unintended changes to existing scope.
Preserve the manifest-to-server ID mapping in protected storage.
Report partial failure without claiming a completed import.

Do not retry automatically: preserve the failure receipt, determine completed operations
and unchanged inputs, then propose the bounded recovery.
Never delete existing cohorts or reset storage to conceal a partial import.
Update the final HTML/report with the actual receipt in a new version; ingestion success
is separate from grading readiness.
