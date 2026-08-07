# Portmanager

Portmanager keeps local development ports stable across many projects and
many coding agents. It gives a workspace one registry, generates per-project
environment files, and installs optional guardrail instructions so agents claim
ports instead of inventing new localhost defaults.

The guardrail installer can add managed policy blocks to agent instruction
files such as `AGENTS.md`, `CLAUDE.md`, and `GEMINI.md`. Home-level Claude
policy uses a path-scoped rule at `~/.claude/rules/portmanager-ports.md` so it
loads only for files that can bind development ports. Managed blocks only write
between `<!-- PORTMANAGER:START -->` and `<!-- PORTMANAGER:END -->`, so existing
human instructions stay intact.

## Why

Local apps tend to drift toward the same ports: `3000`, `5173`, `8000`, `5432`.
That is annoying for one developer and worse when several agents edit different
projects at once. Portmanager makes port ownership explicit:

- `ports.toml` is the canonical registry.
- `ports.lock.json` is a generated machine-readable snapshot.
- `PORTS.md` is a generated human-readable topology report.
- `.portmanager/ports.env` gives each project `PM_PORT_*` and `PM_URL_*` values.

Registry files can expose private project names and paths, so this repository
does not track real local registry state. See `examples/ports.toml` for a
sanitized example.

## Install

For local development:

```bash
uv sync --extra dev
uv run portmanager --help
```

For use as a CLI from other projects:

```bash
uv tool install -e .
portmanager --help
```

## Quickstart

Create a registry in the current workspace:

```bash
portmanager init
```

Inspect discovered port declarations:

```bash
portmanager scan
portmanager scan --json
```

Adopt existing project bindings:

```bash
portmanager adopt /absolute/project/path --dry-run
portmanager adopt /absolute/project/path
```

When two discovered bindings share a service name — a `db` in `docker-compose.yml`
and another in `deploy/compose/.env` — adopt suffixes both with their port
(`db-5432`, `db-5433`) so neither is lost.

Register a standalone project outside the configured discovery roots:

```bash
portmanager projects add /absolute/project/path
portmanager projects add /absolute/external/path --status external
portmanager projects list
```

An `external` project is reservation-only. Portmanager holds its ports so
auto-assign never hands them out, but does not scan the tree, generate
`.portmanager` files, or write guardrail instruction files into it. Use it for a
port owned by something outside the managed workspaces; without it, such a port
ends up filed under an unrelated project and every `doctor` run reports a
conflict that is not real.

Move a service between lifecycle states without releasing and re-claiming it:

```bash
portmanager set-status /absolute/project/path api external --notes "upstream default port"
```

`active` means portmanager assigned the port and validates it. `external` means
the port is reserved but managed elsewhere, so range and conflict checks are
skipped. `retired` returns the port to the pool.

Claim a new managed port:

```bash
portmanager claim /absolute/project/path web --kind web
```

Clean up or migrate registry entries without hand-editing TOML:

```bash
portmanager rename-service /absolute/project/path web frontend
portmanager move-project /old/project/path /new/project/path
portmanager release /absolute/project/path frontend
```

Generate project env files and run a command with those values loaded:

```bash
portmanager sync /absolute/project/path
portmanager run /absolute/project/path -- npm run dev
```

Validate the registry:

```bash
portmanager doctor --all
```

Install optional guardrail instructions for supported agent surfaces:

```bash
portmanager guardrails install --dry-run
portmanager guardrails install
```

The dry run prints every instruction file Portmanager would touch before it
writes anything. Typical targets include:

- `~/.codex/AGENTS.md` and workspace/project `AGENTS.md` files for Codex.
- `~/.claude/rules/portmanager-ports.md` and workspace/project `CLAUDE.md` files
  for Claude.
- `~/.gemini/GEMINI.md` for Gemini.
- `~/.gemini/antigravity/global_workflows/portmanager_policy.md` for
  Antigravity.

Print shell completions:

```bash
portmanager completions bash
portmanager completions zsh
```

## Registry Lookup

Portmanager resolves the registry in this order:

1. `--registry /path/to/ports.toml`
2. `PORTMANAGER_REGISTRY`
3. the nearest `ports.toml` in the current directory or an ancestor
4. the path written in `<user config dir>/registry-path` (a one-line pointer file pinning a canonical registry so claims resolve correctly from any working directory)
5. the user config path under `PORTMANAGER_HOME` or `XDG_CONFIG_HOME`
6. `~/.config/portmanager/ports.toml`

`claim` refuses to run against a registry file that does not exist or a project
outside the registry's roots and explicit project entries. Auto-assign skips
ports registered to any active or external service, ports with live TCP
listeners, and ports that fail a bind probe. Explicit `--port` claims require
`--adopt-existing` and are reserved for pre-existing hardcoded bindings; prefer
auto-assign for new bindings. Successful `claim` and `sync` commands run a
project-scoped `doctor` automatically and exit non-zero on findings.
`--no-doctor` is available for deliberate exceptional use.

`portmanager init` creates `ports.toml` in the current directory unless
`--registry` is supplied.

## Scanner Coverage

The scanner currently understands common local port declarations in:

- `package.json` scripts for Vite, Next.js, Astro, Expo, Uvicorn, Flask,
  Django, Rails, Streamlit, and `python -m http.server`
- `vite.config.ts` and `vite.config.js`
- Docker Compose files
- `pyproject.toml` declarations under `[tool.portmanager.services.<name>]`
- `Makefile` and `Procfile` commands for the same common dev servers
- `app.py`, `main.py`, and `server.py` literals for simple Python server entry
  points
- `.env`, `.env.local`, `.env.development`, and `.env.example`

It classifies owned host-bound listeners as bindings and reports integration
ports such as SMTP, IMAP, local LLM endpoints, and dependency URLs as
references.

## Guardrails

`portmanager guardrails install` writes managed policy blocks to supported
agent instruction files in the user home directory and configured workspace
roots. It also owns Claude's path-scoped home rule file, whose generated header
warns that manual edits are overwritten. Marker-based targets update only the
managed block between:

```md
<!-- PORTMANAGER:START -->
<!-- PORTMANAGER:END -->
```

Use `--dry-run` to preview target files before writing.

Supported instruction targets:

| Surface | Home-level target | Workspace/project target |
| --- | --- | --- |
| Codex | `~/.codex/AGENTS.md` | `AGENTS.md` |
| Claude | `~/.claude/rules/portmanager-ports.md` | `CLAUDE.md` |
| Gemini | `~/.gemini/GEMINI.md` | `GEMINI.md` |
| Antigravity | `~/.gemini/antigravity/global_workflows/portmanager_policy.md` | n/a |

Workspace and project targets are discovered from the active registry roots and
active or external project entries.

## Validation

```bash
uv run pytest
portmanager doctor --all
```

`doctor` fails on unmanaged app-owned bindings, duplicate registry ports,
out-of-range active assignments, missing source files, and source drift in
supported config types.

`doctor --all` additionally reports `unregistered_managed_port`: a live listener
on a port inside the managed range that no registry entry governs. Every other
check starts from a registry entry, so without this a process squatting an
unclaimed managed port stays invisible — auto-assign silently skips the port and
nothing says why. The check is registry-wide, so a project-scoped `doctor` does
not report it.

Listeners are checked only when their bind address overlaps the registered
service host, then attributed to projects by process working directory or
absolute project paths in the process command line. Docker Desktop port proxies
are attributed via the owning container's Compose working-directory label or
bind-mount source paths, so project-owned Compose and plain `docker run`
containers do not trigger `port_in_use`.

Use `doctor --json` when another tool or agent needs stable error codes:

```json
{
  "ok": false,
  "errors": [
    {
      "code": "unmanaged_binding",
      "message": "unmanaged binding in ...",
      "project": "/path/to/project",
      "service": "web",
      "port": 5190
    }
  ]
}
```
