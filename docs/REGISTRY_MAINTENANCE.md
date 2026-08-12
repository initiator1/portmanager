# Registry Maintenance

Long-lived workspaces drift. Registries get shadowed, ports get claimed twice,
and processes outside the workspace squat on managed ports. This document
describes the three repair passes Portmanager supports, and which `doctor`
findings are expected rather than actionable.

All examples use placeholder project and service names. Registry contents are
workspace-specific and should not be committed to a public repository.

## Shadow Registries

A shadow registry is a second `ports.toml` that shadows the canonical one,
usually left behind when a workspace moves or when a user-config registry is
created before the workspace registry exists.

Confirm which registry is authoritative:

```bash
portmanager doctor --all --json
```

Merge each shadow entry into the canonical registry, then retire the shadow so
it can never load again:

```bash
portmanager claim <project> <service>          # auto-assign; never pass --port
mv ~/.config/portmanager/ports.toml ~/.config/portmanager/ports.toml.retired
```

Rules that matter during a merge:

- Preserve the shadow port only when it is free in the canonical registry.
- When the port is already owned, let auto-assign pick a new one, then update
  the project's own source binding (`package.json`, `vite.config.ts`,
  `config.py`, or generated `ports.env`).
- Retire entries whose source binding no longer exists. A registry entry with
  no consumer is drift, not a claim.
- Restart any long-running service whose port changed. The registry is not the
  source of truth for a process that is already listening.

Back up both registries before starting. The merge rewrites claims.

## Duplicate Active Ports

Two projects can end up claiming one port after a rename, a clone, or a manual
edit. `doctor` reports these as conflicts.

Resolve by keeping the live listener and moving the other:

```bash
portmanager doctor --all              # identify the duplicate
portmanager claim <project> <service> # auto-assign a free port for the loser
portmanager sync <project>            # regenerate ports.env
```

Keep the binding that is currently serving traffic. Update the moved project's
source file in the same change, then restart it. A moved claim that leaves a
hardcoded port behind reintroduces the conflict on the next run.

Clones deserve attention: a project copied from another keeps the original's
claims. Mark the clone retired rather than letting both hold live entries.

## Expected Doctor Findings

Some findings are correct and not worth chasing:

- **Docker-backed services report a foreign process.** Docker's port proxy owns
  the listener, so the process cannot be attributed to a project by PID.
  Compose working-dir labels resolve most of these; the rest are acceptable.
- **Listeners outside the managed workspace.** A script living outside the
  workspace can hold a managed port. Either move it onto a claimed port or
  re-claim the service that lost the port.
- **Supervised processes respawn after being killed.** A process manager such
  as launchd, systemd, or pm2 restarts its child. Remove the supervision entry
  before expecting the port to stay free.

Record the outcome of a maintenance pass in your own workspace notes. Those
notes name real projects and ports, so keep them out of version control.
