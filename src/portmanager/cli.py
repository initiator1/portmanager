from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from .config import REGISTRY_FILE_NAME, registry_lock, resolve_registry_path
from .guardrails import install_guardrails, planned_guardrail_targets
from .models import RootEntry
from .registry import (
    build_scan_payload,
    default_registry,
    load_listeners,
    load_registry,
    next_free_port,
    resolve_project_argument,
    upsert_service,
    validate_registry,
    write_generated_artifacts,
    write_project_sync_files,
    write_registry,
)
from .scanner import discover_project_ports


def _package_version() -> str:
    try:
        return version("portmanager")
    except PackageNotFoundError:
        return "0.0.0"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="portmanager")
    parser.add_argument("--registry", help="Path to ports.toml. Defaults to PORTMANAGER_REGISTRY, nearest ports.toml, or user config.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {_package_version()}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create a registry in this workspace")
    init_parser.add_argument("--root", action="append", help="Workspace root to scan. Defaults to the current directory.")
    init_parser.add_argument("--range-start", type=int, default=5190)
    init_parser.add_argument("--range-end", type=int, default=5299)
    init_parser.add_argument("--force", action="store_true")
    init_parser.add_argument("--dry-run", action="store_true")

    scan_parser = subparsers.add_parser("scan", help="Scan configured projects for port bindings")
    scan_parser.add_argument("--json", action="store_true", dest="as_json")

    claim_parser = subparsers.add_parser("claim", help="Claim a stable managed port for a project service")
    claim_parser.add_argument("project")
    claim_parser.add_argument("service")
    claim_parser.add_argument("--kind", required=True, choices=["web", "api", "db", "redis", "worker", "other"])
    claim_parser.add_argument("--port", type=int)
    claim_parser.add_argument("--source-file", default="")
    claim_parser.add_argument("--bind-host", default="127.0.0.1")
    claim_parser.add_argument("--notes", default="")
    claim_parser.add_argument("--dry-run", action="store_true")

    release_parser = subparsers.add_parser("release", help="Retire a project service assignment")
    release_parser.add_argument("project")
    release_parser.add_argument("service")
    release_parser.add_argument("--notes", default="Retired through portmanager release.")
    release_parser.add_argument("--dry-run", action="store_true")

    rename_parser = subparsers.add_parser("rename-service", help="Rename a service within a project")
    rename_parser.add_argument("project")
    rename_parser.add_argument("old_service")
    rename_parser.add_argument("new_service")
    rename_parser.add_argument("--dry-run", action="store_true")

    move_parser = subparsers.add_parser("move-project", help="Move registry entries from one project path to another")
    move_parser.add_argument("old_project")
    move_parser.add_argument("new_project")
    move_parser.add_argument("--dry-run", action="store_true")

    adopt_parser = subparsers.add_parser("adopt", help="Register discovered existing bindings for a project")
    adopt_parser.add_argument("project")
    adopt_parser.add_argument("--dry-run", action="store_true")
    adopt_parser.add_argument("--json", action="store_true", dest="as_json")

    sync_parser = subparsers.add_parser("sync", help="Generate .portmanager files for a project")
    sync_parser.add_argument("project")
    sync_parser.add_argument("--dry-run", action="store_true")

    doctor_parser = subparsers.add_parser("doctor", help="Validate registry state and project drift")
    doctor_parser.add_argument("project", nargs="?")
    doctor_parser.add_argument("--all", action="store_true")
    doctor_parser.add_argument("--json", action="store_true", dest="as_json")

    run_parser = subparsers.add_parser("run", help="Load synced env and run a project command")
    run_parser.add_argument("project")
    run_parser.add_argument("command", nargs=argparse.REMAINDER)

    roots_parser = subparsers.add_parser("roots", help="Manage discovery roots")
    roots_subparsers = roots_parser.add_subparsers(dest="roots_command", required=True)
    roots_add = roots_subparsers.add_parser("add", help="Add a discovery root")
    roots_add.add_argument("path")
    roots_add.add_argument("--dry-run", action="store_true")
    roots_subparsers.add_parser("list", help="List configured roots")

    guardrails_parser = subparsers.add_parser("guardrails", help="Install/update cross-agent guardrails")
    guardrails_subparsers = guardrails_parser.add_subparsers(dest="guardrails_command", required=True)
    guardrails_install = guardrails_subparsers.add_parser("install", help="Install guardrail blocks")
    guardrails_install.add_argument("--dry-run", action="store_true")

    return parser


def _registry_path(args: argparse.Namespace) -> Path:
    return resolve_registry_path(getattr(args, "registry", None))


def _display_source(project: str | Path, source_file: str) -> str:
    if not source_file:
        return "-"
    project_path = Path(project).expanduser().resolve()
    source_path = Path(source_file).expanduser()
    if not source_path.is_absolute():
        return source_file
    try:
        return str(source_path.resolve().relative_to(project_path))
    except ValueError:
        return str(source_path.resolve())


def cmd_init(args: argparse.Namespace) -> int:
    registry_path = Path(args.registry).expanduser().resolve() if args.registry else (Path.cwd() / REGISTRY_FILE_NAME).resolve()
    if args.dry_run:
        action = "would overwrite" if registry_path.exists() and args.force else "would create"
        if registry_path.exists() and not args.force:
            action = "registry already exists"
        print(f"{action} {registry_path}")
        roots = [Path(path).expanduser().resolve() for path in args.root] if args.root else [Path.cwd().resolve()]
        for root in roots:
            print(f"root {root}")
        return 0
    roots = [Path(path).expanduser().resolve() for path in args.root] if args.root else [Path.cwd().resolve()]
    with registry_lock(registry_path):
        if registry_path.exists() and not args.force:
            print(f"ERROR: registry already exists: {registry_path}", file=sys.stderr)
            return 1
        registry = default_registry(roots[0])
        registry.roots = [RootEntry(str(root)) for root in roots]
        registry.managed_range_start = args.range_start
        registry.managed_range_end = args.range_end
        write_registry(registry, registry_path)
        write_generated_artifacts(registry, registry_path)
    print(registry_path)
    return 0


def cmd_scan(args: argparse.Namespace) -> int:
    registry = load_registry(_registry_path(args))
    payload = build_scan_payload(registry, listeners=load_listeners())
    if args.as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    for project_path, project_info in sorted(payload["projects"].items()):
        print(f"[{project_path}] {project_info['classification']}")
        bindings = project_info["bindings"]
        references = project_info["references"]
        registered_only = project_info["registered_only_services"]
        if not bindings and not references and not registered_only:
            print("  no relevant port declarations found")
            continue
        for item in bindings:
            alias_text = f" aliases={','.join(item['aliases'])}" if item["aliases"] else ""
            print(f"  binding    {item['port']:5} {item['service']:18} {_display_source(project_path, item['source_file'])}{alias_text}")
        for item in registered_only:
            print(f"  registry   {item['port']:5} {item['service']:18} {_display_source(project_path, item['source_file'])}")
        for item in references:
            print(f"  reference  {item['port']:5} {item['service']:18} {_display_source(project_path, item['source_file'])}")
        for item in project_info["unmanaged_bindings"]:
            print(f"  unmanaged  {item['port']:5} {item['service']:18} {_display_source(project_path, item['source_file'])}")
    if payload["listeners"]:
        print("\nActive listeners:")
        for port, items in sorted((int(port), items) for port, items in payload["listeners"].items()):
            names = ", ".join(sorted({listener["process"] for listener in items}))
            print(f"  {port}: {names}")
    return 0


def cmd_claim(args: argparse.Namespace) -> int:
    registry_path = _registry_path(args)
    with registry_lock(registry_path):
        registry = load_registry(registry_path)
        project = resolve_project_argument(registry, args.project)
        listeners = load_listeners()
        port = args.port or next_free_port(registry, listeners)
        if args.dry_run:
            print(f"would claim {port} for {project}:{args.service}")
            return 0
        upsert_service(
            registry,
            project=project,
            service_name=args.service,
            kind=args.kind,
            port=port,
            bind_host=args.bind_host,
            source_file=args.source_file,
            notes=args.notes,
        )
        write_registry(registry, registry_path)
        write_generated_artifacts(registry, registry_path)
    print(f"claimed {port} for {project}:{args.service}")
    return 0


def cmd_release(args: argparse.Namespace) -> int:
    registry_path = _registry_path(args)
    with registry_lock(registry_path):
        registry = load_registry(registry_path)
        project = resolve_project_argument(registry, args.project)
        service = registry.service_for(project, args.service)
        if service is None:
            print(f"ERROR: no service named {args.service} for {project}", file=sys.stderr)
            return 1
        if args.dry_run:
            print(f"would retire {project}:{args.service}")
            return 0
        service.status = "retired"
        service.notes = args.notes
        write_registry(registry, registry_path)
        write_generated_artifacts(registry, registry_path)
    print(f"retired {project}:{args.service}")
    return 0


def cmd_rename_service(args: argparse.Namespace) -> int:
    registry_path = _registry_path(args)
    with registry_lock(registry_path):
        registry = load_registry(registry_path)
        project = resolve_project_argument(registry, args.project)
        service = registry.service_for(project, args.old_service)
        if service is None:
            print(f"ERROR: no service named {args.old_service} for {project}", file=sys.stderr)
            return 1
        if registry.service_for(project, args.new_service) is not None:
            print(f"ERROR: service already exists: {project}:{args.new_service}", file=sys.stderr)
            return 1
        if args.dry_run:
            print(f"would rename {project}:{args.old_service} to {args.new_service}")
            return 0
        service.service = args.new_service
        write_registry(registry, registry_path)
        write_generated_artifacts(registry, registry_path)
    print(f"renamed {project}:{args.old_service} to {args.new_service}")
    return 0


def cmd_move_project(args: argparse.Namespace) -> int:
    registry_path = _registry_path(args)
    with registry_lock(registry_path):
        registry = load_registry(registry_path)
        old_project = resolve_project_argument(registry, args.old_project)
        new_project = Path(args.new_project).expanduser().resolve()
        changed = 0
        for project in registry.projects:
            if project.path_obj == old_project:
                project.path = str(new_project)
                changed += 1
        for service in registry.services:
            if service.project_path == old_project:
                service.project = str(new_project)
                changed += 1
        if changed == 0:
            print(f"ERROR: no registry entries found for {old_project}", file=sys.stderr)
            return 1
        if args.dry_run:
            print(f"would move {changed} entries from {old_project} to {new_project}")
            return 0
        write_registry(registry, registry_path)
        write_generated_artifacts(registry, registry_path)
    print(f"moved {changed} entries from {old_project} to {new_project}")
    return 0


def cmd_adopt(args: argparse.Namespace) -> int:
    registry_path = _registry_path(args)
    with registry_lock(registry_path):
        registry = load_registry(registry_path)
        project = resolve_project_argument(registry, args.project)
        assigned = {service.port for service in registry.services_for_project(project) if service.status in {"active", "external"}}
        active_ports = registry.active_ports()
        candidates: list[dict[str, object]] = []
        for item in discover_project_ports(project, registry):
            if item.role != "binding" or item.port in assigned:
                continue
            status = "active" if registry.managed_range_start <= item.port <= registry.managed_range_end else "external"
            candidates.append(
                {
                    "project": str(project),
                    "service": item.service,
                    "kind": item.kind,
                    "port": item.port,
                    "bind_host": item.bind_host,
                    "source_file": _display_source(project, item.source_file),
                    "status": status,
                    "conflict": item.port in active_ports,
                }
            )
        if args.as_json:
            print(json.dumps({"project": str(project), "candidates": candidates}, indent=2, sort_keys=True))
        else:
            if not candidates:
                print("no unmanaged bindings found")
            for candidate in candidates:
                action = "would adopt" if args.dry_run else "adopted"
                conflict = " conflict" if candidate["conflict"] else ""
                print(f"{action} {candidate['port']} {candidate['service']} [{candidate['status']}]{conflict}")
        if args.dry_run or not candidates:
            return 0
        if any(candidate["conflict"] for candidate in candidates):
            print("ERROR: refusing to adopt bindings with active registry port conflicts", file=sys.stderr)
            return 1
        for candidate in candidates:
            upsert_service(
                registry,
                project=project,
                service_name=str(candidate["service"]),
                kind=str(candidate["kind"]),
                port=int(candidate["port"]),
                bind_host=str(candidate["bind_host"]),
                source_file=str(candidate["source_file"]),
                status=str(candidate["status"]),
                notes="Adopted from existing local config.",
            )
        write_registry(registry, registry_path)
        write_generated_artifacts(registry, registry_path)
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    registry_path = _registry_path(args)
    registry = load_registry(registry_path)
    project = resolve_project_argument(registry, args.project)
    if args.dry_run:
        print(project / ".portmanager" / "ports.env")
        print(project / ".portmanager" / "ports.json")
        return 0
    env_path, json_path = write_project_sync_files(registry, project)
    write_generated_artifacts(registry, registry_path)
    print(env_path)
    print(json_path)
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    registry = load_registry(_registry_path(args))
    project = None if args.all or not args.project else resolve_project_argument(registry, args.project)
    errors = validate_registry(registry, project_filter=project)
    if args.as_json:
        print(json.dumps({"ok": not errors, "errors": [error.to_dict() for error in errors]}, indent=2))
    else:
        if errors:
            for error in errors:
                print(f"ERROR: {error}")
        else:
            print("doctor: ok")
    return 1 if errors else 0


def _load_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text(errors="ignore").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        env[key] = value
    return env


def cmd_run(args: argparse.Namespace) -> int:
    registry = load_registry(_registry_path(args))
    project = resolve_project_argument(registry, args.project)
    write_project_sync_files(registry, project)
    errors = validate_registry(registry, project_filter=project)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    if not args.command:
        print("ERROR: no command supplied", file=sys.stderr)
        return 1
    command = args.command[1:] if args.command and args.command[0] == "--" else args.command
    env = os.environ.copy()
    env.update(_load_env_file(project / ".portmanager" / "ports.env"))
    result = subprocess.run(command, cwd=project, env=env, check=False)
    return result.returncode


def cmd_roots_add(args: argparse.Namespace) -> int:
    registry_path = _registry_path(args)
    with registry_lock(registry_path):
        registry = load_registry(registry_path)
        new_root = Path(args.path).expanduser().resolve()
        if args.dry_run:
            print(f"would add root {new_root}")
            return 0
        if all(root.path_obj != new_root for root in registry.roots):
            registry.roots.append(RootEntry(str(new_root)))
        write_registry(registry, registry_path)
        write_generated_artifacts(registry, registry_path)
    print(new_root)
    return 0


def cmd_roots_list(args: argparse.Namespace) -> int:
    registry = load_registry(_registry_path(args))
    for root in registry.roots:
        print(root.path)
    if registry.projects:
        print("\nExplicit projects:")
        for project in registry.projects:
            print(f"{project.path} [{project.status}]")
    return 0


def cmd_guardrails_install(args: argparse.Namespace) -> int:
    registry_path = _registry_path(args)
    registry = load_registry(registry_path)
    if args.dry_run:
        for path in planned_guardrail_targets(registry):
            print(path)
        return 0
    touched = install_guardrails(registry)
    write_generated_artifacts(registry, registry_path)
    for path in touched:
        print(path)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "init":
        return cmd_init(args)
    if args.command == "scan":
        return cmd_scan(args)
    if args.command == "claim":
        return cmd_claim(args)
    if args.command == "release":
        return cmd_release(args)
    if args.command == "rename-service":
        return cmd_rename_service(args)
    if args.command == "move-project":
        return cmd_move_project(args)
    if args.command == "adopt":
        return cmd_adopt(args)
    if args.command == "sync":
        return cmd_sync(args)
    if args.command == "doctor":
        return cmd_doctor(args)
    if args.command == "run":
        return cmd_run(args)
    if args.command == "roots":
        if args.roots_command == "add":
            return cmd_roots_add(args)
        return cmd_roots_list(args)
    if args.command == "guardrails":
        return cmd_guardrails_install(args)
    parser.error(f"unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
