# Portmanager

Portmanager keeps local development ports stable across many projects and
many coding agents. It gives a workspace one registry, generates per-project
environment files, and installs optional guardrail instructions so agents claim
ports instead of inventing new localhost defaults.

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
4. the user config path under `PORTMANAGER_HOME` or `XDG_CONFIG_HOME`
5. `~/.config/portmanager/ports.toml`

`portmanager init` creates `ports.toml` in the current directory unless
`--registry` is supplied.

## Scanner Coverage

The scanner currently understands common local port declarations in:

- `package.json` scripts for Vite, Next.js, and Uvicorn
- `vite.config.ts` and `vite.config.js`
- Docker Compose files
- `pyproject.toml` declarations under `[tool.portmanager.services.<name>]`
- `Makefile` and `Procfile` commands for Uvicorn, Streamlit, and
  `python -m http.server`
- `.env`, `.env.local`, `.env.development`, and `.env.example`

It classifies owned host-bound listeners as bindings and reports integration
ports such as SMTP, IMAP, local LLM endpoints, and dependency URLs as
references.

## Guardrails

`portmanager guardrails install` writes managed policy blocks to supported
agent instruction files in the user home directory and configured workspace
roots. The command updates only the managed block between:

```md
<!-- PORTMANAGER:START -->
<!-- PORTMANAGER:END -->
```

Use `--dry-run` to preview target files before writing.

## Validation

```bash
uv run pytest
portmanager doctor --all
```

`doctor` fails on unmanaged app-owned bindings, duplicate registry ports,
out-of-range active assignments, missing source files, and source drift in
supported config types.

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
