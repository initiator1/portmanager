# Demo Walkthrough

The fixture under `examples/demo-workspace` shows Portmanager operating on a
small workspace with a frontend app, API app, and Docker-backed database.

From the repository root:

```bash
tmpdir="$(mktemp -d)"
cp -R examples/demo-workspace "$tmpdir/workspace"
cd "$tmpdir/workspace"

portmanager init
portmanager scan
portmanager adopt "$tmpdir/workspace/frontend" --dry-run
portmanager adopt "$tmpdir/workspace/frontend"
portmanager adopt "$tmpdir/workspace/api"
portmanager adopt "$tmpdir/workspace/infra"
portmanager doctor --all
```

Expected result: the scan shows unmanaged bindings first, adoption registers
them, and `doctor --all` succeeds after all owned bindings are represented in
`ports.toml`.

