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
- Added GitHub Actions CI for Python 3.11, 3.12, and 3.13.
- Added a release checklist and demo workspace.
- Added structured `doctor --json` validation errors for agent integrations.
- Added scanner coverage for `[tool.portmanager.services]`, Makefile, and
  Procfile declarations.
- Added registry file locking around mutating CLI commands.

## Remaining Before Public Release

- Decide on the first public distribution channel.
- Add scanner support for more frameworks.
- Add shell completions.
- Decide whether to publish to PyPI, Homebrew, or both.
