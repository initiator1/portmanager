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
- Added scanner coverage for `[tool.portmanager.services]`, Makefile, Procfile,
  common Node/Python dev-server commands, and simple Python server entry
  points.
- Added registry file locking around mutating CLI commands.
- Added bash and zsh completion script generation.
- Added a tag-driven GitHub release workflow for built artifacts.

## Remaining Before External Publication

- Confirm package-name availability on PyPI immediately before first upload.
- Create and push the GitHub repository.
- Decide whether the first external publication includes PyPI or only GitHub
  Releases.
