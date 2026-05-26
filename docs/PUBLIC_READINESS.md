# Public Readiness

This document tracks the work needed before publishing Portmanager outside a
personal workstation.

## Completed In This Slice

- Removed user-specific defaults from package constants.
- Added registry lookup through `--registry`, `PORTMANAGER_REGISTRY`, nearest
  workspace registry, and user config paths.
- Added `portmanager init` for first-run setup.
- Added dry-run support for high-risk mutations.
- Added `adopt`, `release`, `rename-service`, and `move-project` lifecycle
  commands.
- Stopped tracking real local registry artifacts by default.
- Added sanitized example registry data.
- Added license, contribution, privacy, and quickstart documentation.
- Added atomic writes for registry, generated reports, sync files, and
  guardrail files.

## Remaining Before Public Release

- Add CI for tests and package build checks.
- Add a release checklist and version bump process.
- Add richer scanner support for more frameworks.
- Add structured error codes for CLI and agent integrations.
- Add file locking for concurrent registry mutation.
- Add shell completions.
- Add a demo fixture workspace and terminal walkthrough.
- Decide whether to publish to PyPI, Homebrew, or both.
