# Changelog

All notable changes to this release unit are documented in this file.

The format is based on Keep a Changelog, and this release unit follows Semantic
Versioning.

## [Unreleased][unreleased]

### Added

### Changed

### Deprecated

### Removed

### Fixed

### Security

## [0.1.0][oasis-ingestion-v0.1.0] - 2026-09-15

### Added

- Added the installable `oasis-ingestion` plugin for Codex CLI and Claude Code.
- Added the `oasis-prepare-ingestion` skill for inventory, mapping review, protected
  package generation, validation, connection setup, and explicit import handoff.
- Added deterministic manifest validation and static HTML review helpers.
- Added a guarded importer runner and private environment setup using an unchanged,
  provenance-recorded OASIS importer, bundled Elephant SDK wheel, and hash-locked
  dependency set.
- Added synthetic portable-runtime tests and plugin smoke validation.

### Changed

- Nothing.

### Deprecated

- Nothing.

### Removed

- Nothing.

### Fixed

- Nothing.

### Security

- Added explicit host/model disclosure gates, protected-log handling, owner-private
  credential checks, bounded paths, immutable-input checks, final byte-and-target
  confirmation, and no-automatic-retry behavior.

[unreleased]: https://github.com/JamiesonLabUTSW/maples-toolkit/compare/oasis-ingestion/v0.1.0...HEAD
[oasis-ingestion-v0.1.0]: https://github.com/JamiesonLabUTSW/maples-toolkit/releases/tag/oasis-ingestion/v0.1.0
