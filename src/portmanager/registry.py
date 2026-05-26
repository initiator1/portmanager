from __future__ import annotations

import json
import os
import socket
import subprocess
import tomllib
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import tomli_w

from .config import artifact_paths, resolve_registry_path, write_text_atomic
from .constants import (
    DEFAULT_BIND_HOST,
    MANAGED_RANGE_END,
    MANAGED_RANGE_START,
)
from .models import DiscoveredPort, Listener, ProjectEntry, Registry, RootEntry, ServiceEntry
from .scanner import discover_all, discover_source_ports

GOVERNING_SERVICE_STATUSES = {"active", "external"}


def default_registry(root: Path | None = None) -> Registry:
    default_root = (root or Path.cwd()).expanduser().resolve()
    return Registry(
        managed_range_start=MANAGED_RANGE_START,
        managed_range_end=MANAGED_RANGE_END,
        roots=[RootEntry(str(default_root))],
        projects=[],
        services=[],
    )


def load_registry(path: Path | str | None = None) -> Registry:
    registry_path = resolve_registry_path(path)
    if not registry_path.exists():
        return default_registry(registry_path.parent)
    data = tomllib.loads(registry_path.read_text())
    return Registry(
        version=int(data.get("version", 1)),
        managed_range_start=int(data.get("managed_range_start", MANAGED_RANGE_START)),
        managed_range_end=int(data.get("managed_range_end", MANAGED_RANGE_END)),
        roots=[RootEntry(**item) for item in data.get("roots", [])],
        projects=[ProjectEntry(**item) for item in data.get("projects", [])],
        services=[ServiceEntry(**item) for item in data.get("services", [])],
    )


def write_registry(registry: Registry, path: Path | str | None = None) -> None:
    registry_path = resolve_registry_path(path)
    payload = {
        "version": registry.version,
        "managed_range_start": registry.managed_range_start,
        "managed_range_end": registry.managed_range_end,
        "roots": [root.to_dict() for root in sorted(registry.roots, key=lambda item: item.path)],
        "projects": [project.to_dict() for project in sorted(registry.projects, key=lambda item: item.path)],
        "services": [service.to_dict() for service in sorted(registry.services, key=lambda item: (item.project, item.port, item.service))],
    }
    write_text_atomic(registry_path, tomli_w.dumps(payload))


def _project_status(registry: Registry, project_path: Path) -> str:
    resolved = project_path.expanduser().resolve()
    for project in registry.projects:
        if project.path_obj == resolved:
            return project.status
    if resolved.name.startswith("!DEPRECATED"):
        return "archived"
    return "active"


def configured_project_paths(registry: Registry) -> list[Path]:
    seen: set[Path] = set()
    project_paths: list[Path] = []
    for root in registry.roots:
        root_path = root.path_obj
        if not root_path.exists():
            continue
        for child in sorted(root_path.iterdir()):
            if not child.is_dir():
                continue
            if child.name.startswith("."):
                continue
            if child.name == "portmanager":
                continue
            resolved = child.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            project_paths.append(resolved)
    for project in registry.projects:
        resolved = project.path_obj
        if resolved in seen or not resolved.exists():
            continue
        seen.add(resolved)
        project_paths.append(resolved)
    return project_paths


def resolve_project_argument(registry: Registry, value: str) -> Path:
    raw_path = Path(value).expanduser()
    if raw_path.is_absolute():
        return raw_path.resolve()
    for project in configured_project_paths(registry):
        if project.name == value or str(project).endswith(value):
            return project.resolve()
    return (Path.cwd() / raw_path).resolve()


def next_free_port(registry: Registry, listeners: dict[int, list[Listener]]) -> int:
    active_ports = registry.active_ports()
    for port in range(registry.managed_range_start, registry.managed_range_end + 1):
        if port in active_ports or port in listeners:
            continue
        return port
    raise RuntimeError("No free managed ports remain in the configured range")


def upsert_service(
    registry: Registry,
    *,
    project: Path,
    service_name: str,
    kind: str,
    port: int,
    bind_host: str = DEFAULT_BIND_HOST,
    source_file: str = "",
    status: str = "active",
    notes: str = "",
) -> ServiceEntry:
    resolved_project = project.expanduser().resolve()
    existing = registry.service_for(resolved_project, service_name)
    if existing is None:
        existing = ServiceEntry(
            project=str(resolved_project),
            status=status,
            service=service_name,
            kind=kind,
            port=port,
            bind_host=bind_host,
            source_file=source_file,
            notes=notes,
        )
        registry.services.append(existing)
        return existing
    existing.status = status
    existing.kind = kind
    existing.port = port
    existing.bind_host = bind_host
    existing.source_file = source_file or existing.source_file
    existing.notes = notes or existing.notes
    return existing


def _governs_discovered_binding(service: ServiceEntry) -> bool:
    return service.status in GOVERNING_SERVICE_STATUSES


def load_listeners() -> dict[int, list[Listener]]:
    command = ["lsof", "-nP", "-iTCP", "-sTCP:LISTEN"]
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    listeners: dict[int, list[Listener]] = defaultdict(list)
    lines = result.stdout.splitlines()
    for line in lines[1:]:
        parts = line.split()
        if len(parts) < 9:
            continue
        name = parts[0]
        endpoint = parts[-1]
        if ":" not in endpoint:
            continue
        port_text = endpoint.rsplit(":", 1)[-1]
        if not port_text.isdigit():
            continue
        listeners[int(port_text)].append(Listener(port=int(port_text), process=name, raw=line))
    return listeners


def generate_project_env(registry: Registry, project_path: Path) -> str:
    services = registry.services_for_project(project_path)
    lines = [
        f"PM_HOST={DEFAULT_BIND_HOST}",
        f"PM_PROJECT={project_path.resolve()}",
    ]
    for service in services:
        env_key = service.env_key
        lines.append(f"PM_PORT_{env_key}={service.port}")
        lines.append(f"PM_URL_{env_key}={service_url(service)}")
    return "\n".join(lines) + "\n"


def service_url(service: ServiceEntry) -> str:
    if service.kind in {"web", "api", "gui", "desktop"}:
        return f"http://{service.bind_host}:{service.port}"
    if service.kind == "redis":
        return f"redis://{service.bind_host}:{service.port}"
    if service.kind == "db":
        return f"postgresql://{service.bind_host}:{service.port}"
    return f"tcp://{service.bind_host}:{service.port}"


def write_project_sync_files(registry: Registry, project_path: Path) -> tuple[Path, Path]:
    target_dir = project_path / ".portmanager"
    target_dir.mkdir(parents=True, exist_ok=True)
    env_path = target_dir / "ports.env"
    json_path = target_dir / "ports.json"
    services = registry.services_for_project(project_path)
    write_text_atomic(env_path, generate_project_env(registry, project_path))
    json_payload = {
        "project": str(project_path.resolve()),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "services": [
            {
                "service": service.service,
                "kind": service.kind,
                "port": service.port,
                "bind_host": service.bind_host,
                "url": service_url(service),
                "source_file": service.source_file,
                "status": service.status,
                "notes": service.notes,
            }
            for service in services
        ],
    }
    write_text_atomic(json_path, json.dumps(json_payload, indent=2, sort_keys=True) + "\n")
    return env_path, json_path


def write_generated_artifacts(registry: Registry, registry_path: Path | str | None = None) -> None:
    lock_path, report_path = artifact_paths(resolve_registry_path(registry_path))
    listeners = load_listeners()
    scan_payload = build_scan_payload(registry, listeners=listeners)
    lock_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "managed_range_start": registry.managed_range_start,
        "managed_range_end": registry.managed_range_end,
        "roots": [root.path for root in registry.roots],
        "projects": [project.to_dict() for project in registry.projects],
        "services": [service.to_dict() for service in sorted(registry.services, key=lambda item: (item.project, item.port, item.service))],
        "listeners": scan_payload["listeners"],
        "project_audit": scan_payload["projects"],
    }
    write_text_atomic(lock_path, json.dumps(lock_payload, indent=2, sort_keys=True) + "\n")
    write_text_atomic(report_path, render_report(registry, scan_payload))


def _project_classification(registry: Registry, project_path: Path, bindings: list[DiscoveredPort], active_services: list[ServiceEntry]) -> str:
    if _project_status(registry, project_path) != "active":
        return "archived"
    if bindings or active_services:
        return "active_app"
    return "non_app"


def build_scan_payload(registry: Registry, listeners: dict[int, list[Listener]] | None = None) -> dict[str, object]:
    active_listeners = listeners if listeners is not None else load_listeners()
    discoveries = discover_all(registry)
    project_payload: dict[str, object] = {}
    for project in configured_project_paths(registry):
        ports = discoveries.get(project, [])
        bindings = [item for item in ports if item.role == "binding"]
        references = [item for item in ports if item.role != "binding"]
        services = registry.services_for_project(project)
        active_services = [service for service in services if service.status == "active"]
        governing_services = [service for service in services if _governs_discovered_binding(service)]
        assigned_ports = {service.port for service in governing_services}
        registered_only = [service for service in active_services if service.port not in {item.port for item in bindings}]
        classification = _project_classification(registry, project, bindings, active_services)
        unmanaged_bindings = [
            item.to_dict()
            for item in bindings
            if classification == "active_app" and item.port not in assigned_ports
        ]
        project_payload[str(project)] = {
            "classification": classification,
            "status": _project_status(registry, project),
            "summary": {
                "governed_port_count": len({service.port for service in governing_services} | {item.port for item in bindings}),
                "binding_count": len(bindings),
                "reference_count": len(references),
                "alias_count": sum(len(item.aliases) for item in bindings),
                "registered_only_count": len(registered_only),
                "unmanaged_count": len(unmanaged_bindings),
            },
            "bindings": [item.to_dict() for item in bindings],
            "references": [item.to_dict() for item in references],
            "registered_services": [service.to_dict() for service in active_services],
            "registered_only_services": [service.to_dict() for service in registered_only],
            "unmanaged_bindings": unmanaged_bindings,
        }
    return {
        "projects": project_payload,
        "listeners": {
            str(port): [listener.to_dict() for listener in items]
            for port, items in sorted(active_listeners.items())
        },
    }


def _relative_path(path_text: str, project_path: Path) -> str:
    path = Path(path_text)
    try:
        return str(path.relative_to(project_path))
    except ValueError:
        return str(path)


def _binding_summary(item: dict[str, object], project_path: Path) -> str:
    alias_text = ""
    aliases = item.get("aliases") or []
    if aliases:
        alias_text = f" aliases: {', '.join(f'`{alias}`' for alias in aliases)}"
    source = _relative_path(str(item["source_file"]), project_path)
    return f"- `{item['port']}` `{item['service']}` [{item['kind']}] from `{source}`{alias_text}"


def _reference_summary(item: dict[str, object], project_path: Path) -> str:
    source = _relative_path(str(item["source_file"]), project_path)
    detail = f" ({item['detail']})" if item.get("detail") else ""
    return f"- `{item['port']}` `{item['service']}` from `{source}`{detail}"


def render_report(registry: Registry, scan_payload: dict[str, object]) -> str:
    projects = scan_payload["projects"]
    listeners = scan_payload["listeners"]
    lines = [
        "# Port Registry",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Roots",
        "",
    ]
    for root in registry.roots:
        lines.append(f"- `{root.path}`")
    if registry.projects:
        lines.extend(["", "## Explicit Projects", ""])
        for project in registry.projects:
            notes = f" ({project.notes})" if project.notes else ""
            lines.append(f"- `{project.path}` [{project.status}]{notes}")
    lines.extend(
        [
            "",
            "## Project Audit",
            "",
            "| Project | Classification | Governed Ports | References | Alias Collapses | Unmanaged |",
            "|---|---|---:|---:|---:|---:|",
        ]
    )
    for project_path, project_info in sorted(projects.items()):
        summary = project_info["summary"]
        lines.append(
            f"| `{project_path}` | `{project_info['classification']}` | `{summary['governed_port_count']}` | "
            f"`{summary['reference_count']}` | `{summary['alias_count']}` | `{summary['unmanaged_count']}` |"
        )
    lines.extend(["", "## Services", "", "| Project | Service | Kind | Port | Status | Source | Notes |", "|---|---|---|---:|---|---|---|"])
    for service in sorted(registry.services, key=lambda item: (item.project, item.port, item.service)):
        source = service.source_file or "-"
        notes = service.notes or "-"
        lines.append(
            f"| `{service.project}` | `{service.service}` | `{service.kind}` | `{service.port}` | `{service.status}` | `{source}` | {notes} |"
        )
    lines.extend(["", "## Active Listeners", ""])
    if not listeners:
        lines.append("- none")
    else:
        for port, items in sorted((int(port), items) for port, items in listeners.items()):
            names = ", ".join(sorted({item["process"] for item in items}))
            lines.append(f"- `{port}`: {names}")
    lines.extend(["", "## Topology", ""])
    for project_path_text, project_info in sorted(projects.items()):
        bindings = project_info["bindings"]
        references = project_info["references"]
        registered_only = project_info["registered_only_services"]
        if not bindings and not references and not registered_only:
            continue
        project_path = Path(project_path_text)
        lines.append(f"### `{project_path_text}` [{project_info['classification']}]")
        lines.append("")
        if bindings:
            lines.append("Unique governed bindings:")
            for item in bindings:
                lines.append(_binding_summary(item, project_path))
        if registered_only:
            if bindings:
                lines.append("")
            lines.append("Registry-only services:")
            for service in registered_only:
                source = _relative_path(service["source_file"], project_path) if service.get("source_file") else "-"
                lines.append(f"- `{service['port']}` `{service['service']}` [{service['kind']}] from `{source}`")
        if references:
            if bindings or registered_only:
                lines.append("")
            lines.append("References:")
            for item in references:
                lines.append(_reference_summary(item, project_path))
        if project_info["unmanaged_bindings"]:
            lines.append("")
            lines.append("Unmanaged bindings:")
            for item in project_info["unmanaged_bindings"]:
                lines.append(_binding_summary(item, project_path))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _source_file_matches_service(service: ServiceEntry) -> bool:
    source_path = service.source_path
    if source_path is None:
        return True
    project_path = service.project_path
    discoveries = discover_source_ports(project_path, source_path)
    bindings = [item for item in discoveries if item.role == "binding"]
    if bindings:
        return any(item.port == service.port for item in bindings)
    text = source_path.read_text(errors="ignore")
    env_marker = f"PM_PORT_{service.env_key}"
    return env_marker in text or str(service.port) in text


def validate_registry(registry: Registry, project_filter: Path | None = None) -> list[str]:
    listeners = load_listeners()
    discoveries = discover_all(registry)
    errors: list[str] = []

    seen_ports: dict[int, ServiceEntry] = {}
    for service in sorted(registry.services, key=lambda item: (item.project, item.port, item.service)):
        if project_filter and service.project_path != project_filter.resolve():
            continue
        if not _governs_discovered_binding(service):
            continue
        if service.status == "active":
            if not registry.managed_range_start <= service.port <= registry.managed_range_end:
                errors.append(f"{service.project}:{service.service} uses out-of-range port {service.port}")
            prior = seen_ports.get(service.port)
            if prior is not None:
                errors.append(
                    f"duplicate active registry port {service.port}: {prior.project}:{prior.service} and {service.project}:{service.service}"
                )
            else:
                seen_ports[service.port] = service
            if service.port in listeners:
                processes = ", ".join(sorted({listener.process for listener in listeners[service.port]}))
                errors.append(f"assigned port {service.port} for {service.project}:{service.service} is already listening ({processes})")

        if service.source_file:
            source_path = service.source_path
            if source_path is None:
                continue
            if not source_path.exists():
                errors.append(f"missing source file for {service.project}:{service.service}: {service.source_file}")
            elif not _source_file_matches_service(service):
                errors.append(
                    f"source file drift for {service.project}:{service.service}: expected managed binding for port {service.port} in {service.source_file}"
                )

    for project_path, ports in discoveries.items():
        if project_filter and project_path.resolve() != project_filter.resolve():
            continue
        if _project_status(registry, project_path) != "active":
            continue
        assigned = {service.port for service in registry.services_for_project(project_path) if _governs_discovered_binding(service)}
        for item in ports:
            if item.role != "binding":
                continue
            if item.port not in assigned:
                errors.append(
                    f"unmanaged binding in {project_path}: port {item.port} from {item.source_file} ({item.service}) is not represented in ports.toml"
                )
    return errors
