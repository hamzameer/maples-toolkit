# Portable importer runtime

This private engineering bundle includes the unchanged CSV importer and SDK from the
exact OASIS commit recorded in `runtime/provenance.json`. It includes an SDK wheel,
retained SDK source/license, and a hash-locked dependency list exported from that
revision's SDK lock.
It is not a public OASIS release, server installer, or proof of compatibility with every
Elephant deployment.
No OASIS binary, Go build, Git checkout, or GitHub login is needed to use it.

## Setup

The host needs Python 3.10+ and either Python's `venv`/`ensurepip` support or an
existing `uv` executable.
The Python setup helper itself does not install Python, uv, or system packages; the
agent guides that prerequisite step first when needed.
Public package-index access is needed for the locked dependencies; only the SDK wheel is
bundled. This is not an offline dependency bundle.

### First-time Python setup

Before calling a Python helper, detect the execution OS and available runtime: use
`python3 --version` on Linux/macOS or `py -3 --version` on Windows.
If the command is absent, check existing user-managed Python/Conda or approved cluster
modules before proposing a new installation.
Do not scan unrelated storage.
On shared HPC, follow the site's supported software route; do not use sudo, replace the
system Python, or initialize/modify a user's shell automatically.

If uv is already available and managed Python downloads are allowed, propose its
user-local Python 3.12 installation:

```bash
uv python install 3.12
uv python find 3.12
```

Use the interpreter path returned by `uv python find` to invoke
`setup_importer.py --venv <private-env-dir> --installer uv`. Do not assume installing
managed Python changes `python3` on PATH. Verify the actual version and record it in the
setup notes. This requires internet access and disk space; explain the installation
before proceeding within the user's setup authority.

If uv is absent, offer either the site's approved Python distribution or the official
Python/uv installation route appropriate to the OS. On a personal Windows machine, a
per-user Python installation with its launcher and venv support is suitable; on a
managed machine, follow the approved software channel.
Use official distribution sources and their available integrity checks, not a pasted
third-party download command.
Prefer user-local installation and make PATH changes explicit.
If installation is blocked, provide exact operator steps and report the missing
prerequisite rather than claiming setup succeeded.

After Python is available, run the isolated importer setup below.
Do not install the SDK dependencies into base Conda or system Python.
Installing Python does not grant access to research data or permission to upload it.

Select a fresh operator-private environment directory outside source payloads and
repositories. Run on the host where ingestion will execute:

```bash
python3 <skill-dir>/scripts/setup_importer.py --venv <private-env-dir>
python3 <skill-dir>/scripts/setup_importer.py --venv <private-env-dir> --check
```

`auto` uses uv when already installed, otherwise pip.
Override with `--installer pip` or `--installer uv`. Setup uses only hash-locked binary
dependency wheels and installs the bundled SDK wheel without dependency resolution.
Unsupported Python/platform wheel combinations fail instead of silently compiling or
changing versions. An existing environment is never overwritten; failed environments
remain for diagnosis.
Retry into a new path.
Windows ACLs need operator verification; POSIX permissions are restricted by the setup
umask. The setup receipt records dependency versions, SDK file hashes, and bundle
identity. Integrity checks detect drift, not a malicious replacement of both files and
their hash inventory; this bundle is not signed.

Linux x86-64/Python 3.12/uv is the tested setup.
Other Python versions and Windows/macOS remain unverified despite the SDK's
platform-neutral wheel.

## Offline preview

No environment setup or key is needed for preparation and dry-run:

```bash
python3 <skill-dir>/scripts/run_import.py dry-run \
  --csv <run-dir>/ingest.csv --data-dir <input-root> \
  --receipt-dir <run-dir>/preview-v1
```

The receipt directory must not exist; its parent must exist.
The runner saves `validation.json`, `import.log`, and `receipt.json` with restricted
permissions. The detailed log can contain learner metadata; do not return it through an
unapproved agent channel.
The console reports only operation status.

## Connection

Use the selected owner-private dotfile containing exactly `ELEPHANT_API_URL` and
`ELEPHANT_API_KEY`. Values can be unquoted or enclosed in matching single or double
quotes. Blank/comment lines are allowed.
Inline comments, multiline values, `export`, additional assignments, and interpolation
are not supported. Nothing in the file is evaluated as shell code.
Never print the file or key.

```bash
python3 <skill-dir>/scripts/run_import.py check-connection \
  --venv <private-env-dir> --config <private-dotfile> \
  --expected-url <reviewed-base-url> \
  --receipt-dir <run-dir>/connection-v1
```

On POSIX, the config and its immediate parent must be owned by the operator with no
group/other permissions (typically 0600 and 0700). On Windows, first verify owner-only
ACLs, then supply `--windows-acl-verified`; the flag records an operator assertion, not
an automated ACL check.
Site-specific ACL policies must be satisfied separately.
The runner permits HTTPS or loopback HTTP for an approved tunnel, rejects
redirects/cross-origin requests, and does not use ambient proxies/netrc.
Custom transport requirements need an explicit adapter, not disabling TLS or request
checks.

This operation tests only health and file-type reads.
It does not prove the key's write role, package clearance, or namespace isolation.
Finish the role and target checks in the connection handoff before offering ingestion.

## Execute after the final confirmation

```bash
python3 <skill-dir>/scripts/run_import.py ingest \
  --venv <private-env-dir> --config <private-dotfile> \
  --expected-url <reviewed-base-url> \
  --csv <run-dir>/ingest.csv --data-dir <input-root> \
  --review-validation <run-dir>/preview-v1/validation.json \
  --receipt-dir <run-dir>/import-v1 --confirm-ingest
```

The flag is supplied only after the user authorizes the exact reviewed package and
target. It is an execution guard, not institutional processing clearance.
The runner recomputes validation and compares it with the reviewed receipt, including
every selected file hash and the exact CSV hash.
Preserve immutable inputs throughout execution; this is a preflight check, not a
filesystem lock. It checks the installed environment before launching the unmodified
importer. Credentials are read locally and never passed as process arguments.
The wrapper rejects redirects, suppresses raw exception traces, and redacts the literal
key in loader output.
Still keep logs protected and avoid HTTP debug logging.
Receipts do not contain credential values.

A zero importer exit is reported as `COMMAND_SUCCEEDED_RECONCILIATION_REQUIRED`, not
completed ingestion.
The current upstream loader has limited bulk-result reporting; inspect failures and
independently reconcile target IDs, counts, membership, and available hashes before
claiming completion.
The runner does not implement that server reconciliation, grading, rollback, or retries.
Keep failed receipts and propose a bounded recovery based on what the server actually
accepted.

## Maintenance

Do not edit `runtime/load-data.py`, SDK source, or the wheel independently.
Refresh them together from an explicitly selected product revision, export its frozen
runtime dependency lock, verify wheel source bytes against that commit, and regenerate
the integrity inventory.
Record the revision and rerun setup, offline checks, and synthetic transport tests
before distributing an update.
Refresh provenance and the package ZIP; never include installed environments,
credentials, learner data, temporary logs, or Python caches.
