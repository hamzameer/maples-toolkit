# Changelog

All notable marketplace, catalog, release automation, and repository tooling changes are
documented in this file.

The format is based on Keep a Changelog, and this release unit follows Semantic
Versioning.

## [Unreleased][unreleased]

### Added

### Changed

### Deprecated

### Removed

### Fixed

### Security

## [0.2.0] - 2026-09-15

### Added

- Added the installable `oasis-ingestion` plugin to the Codex and Claude Code
  marketplaces.

### Changed

- Updated marketplace documentation and validation for two available plugin release
  units.

### Deprecated

- Nothing.

### Removed

- Nothing.

### Fixed

- Expanded root CI coverage to lint and format-check the OASIS ingestion skill scripts
  and tests and type-check both surfaces.

### Security

- Added marketplace distribution for a guarded ingestion plugin that keeps credentials
  and protected data outside repository metadata.

## [0.1.0] - 2026-05-24

### Added

- Established the initial MAPLES plugin marketplace catalog for Codex CLI and Claude
  Code.
- Added the installable `rubric-maker-skill` plugin entry.
- Added Codex placeholder catalog entries for `case-generation` and
  `validation-analysis` with `NOT_AVAILABLE` installation policy.
- Added marketplace compatibility, schema sync, grade-sheet sync, and plugin smoke
  checks through the root Makefile.
- Added independent plugin and marketplace release policy, SemVer rules, changelog
  requirements, namespaced tag conventions, and maintainer release procedures.
- Added version, changelog, and release-readiness validation scripts with Makefile
  targets.
- Added pull request changelog gating, manual release readiness workflow, and
  tag-triggered draft GitHub Release workflow.
- Added release triage labels for release, marketplace, automation, plugin-specific, and
  no-release workflows.

### Changed

- Documented the marketplace layout and local development checks.
- Removed duplicate plugin-entry version metadata from the Claude marketplace so plugin
  manifest versions remain the source of truth.

### Deprecated

- Nothing.

### Removed

- Nothing.

### Fixed

- Nothing.

### Security

- Added packaging hygiene checks for generated archives, OS metadata, caches, local
  environments, logs, and generated output directories.

[unreleased]: https://github.com/JamiesonLabUTSW/maples-toolkit/compare/marketplace/v0.2.0...HEAD
[0.1.0]: https://github.com/JamiesonLabUTSW/maples-toolkit/releases/tag/marketplace/v0.1.0
[0.2.0]: https://github.com/JamiesonLabUTSW/maples-toolkit/releases/tag/marketplace/v0.2.0
