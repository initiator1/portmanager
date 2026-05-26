# Contributing

Portmanager is early-stage software. Keep changes small, tested, and focused on
local development port governance.

## Development

```bash
uv sync --extra dev
uv run pytest
```

## Pull Requests

- Include tests for parser, registry, or CLI behavior changes.
- Avoid committing real `ports.toml`, `ports.lock.json`, or `PORTS.md` files
  from a personal machine.
- Keep new scanner rules conservative. A false positive can block unrelated
  local workspaces.
- Prefer dry-run or preview behavior before adding a mutating command.

## Privacy

Registry and report files may contain private project names, filesystem paths,
service names, and active listener process names. Use fixtures or sanitized
examples in issues and pull requests.
