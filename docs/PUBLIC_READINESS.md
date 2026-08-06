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

## Published State

- The GitHub repository is public.
- The first release is published through GitHub Releases.
- The release intentionally ships source and wheel artifacts only.
- PyPI publication remains optional and should be checked separately before any
  package-index upload.

## Documentation Gaps To Keep Visible

- Guardrail installation should stay prominent in public docs because it writes
  managed policy blocks to agent instruction files such as `AGENTS.md`,
  `CLAUDE.md`, and `GEMINI.md`.
- Any future release notes should call out whether guardrail target coverage has
  changed.

## Guardrail Target Coverage Changes

Call these out in release notes.

- Claude's home-level target moved from `~/.claude/CLAUDE.md` to the path-scoped
  rule `~/.claude/rules/portmanager-ports.md`. `guardrails install` now removes a
  managed block it previously wrote to `~/.claude/CLAUDE.md`; `--dry-run` lists
  that removal. Codex, Gemini, Antigravity, and all workspace/project targets are
  unchanged.
