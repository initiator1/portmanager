from __future__ import annotations

import json
import os
import re
from pathlib import Path

import yaml

from .constants import IGNORED_DIRS, SCAN_FILE_NAMES
from .models import DiscoveredPort, Registry

PORT_KEY_RE = re.compile(r"(?P<key>[A-Z0-9_]+)\s*=\s*(?P<value>.+)")
URL_PORT_RE = re.compile(r"(?P<scheme>[a-z]+)://(?:localhost|127\.0\.0\.1|0\.0\.0\.0):(?P<port>\d{2,5})", re.IGNORECASE)
NEXT_PORT_RE = re.compile(r"next\s+dev\b[^\n]*?--port(?:=|\s+)(?P<value>\$\{[^}]+\}|\d{2,5})")
VITE_SCRIPT_PORT_RE = re.compile(r"\bvite(?:\s+\w+)?\b[^\n]*?--port(?:=|\s+)(?P<value>\$\{[^}]+\}|\d{2,5})")
UVICORN_PORT_RE = re.compile(r"uvicorn\b[^\n]*?--port(?:=|\s+)(?P<value>\$\{[^}]+\}|\d{2,5})")
ENV_FALLBACK_PORT_RE = re.compile(r"\$\{[A-Z0-9_]+(?::-|-)(?P<port>\d{2,5})\}")
JS_ENV_PORT_ASSIGN_RE = re.compile(
    r"(?:const|let|var)\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*Number\(\s*process\.env\.(?P<env>[A-Z0-9_]+)\s*(?:\?\?|\|\|)\s*(?P<port>\d{2,5})\s*\)"
)
SERVER_PORT_TOKEN_RE = re.compile(r"server\s*:\s*{[\s\S]*?\bport\s*:\s*(?P<token>[A-Za-z_][A-Za-z0-9_]*|\d{2,5})")
HMR_PORT_TOKEN_RE = re.compile(
    r"hmr\s*:\s*(?:[^{}]*\?)?\s*{[\s\S]*?\bport\s*:\s*(?P<token>[A-Za-z_][A-Za-z0-9_]*|\d{2,5})"
)
COMPOSE_PORT_MAPPING_RE = re.compile(
    r"^(?:(?P<bind_host>[^:]+):)?(?P<published>\$\{[^}]+\}|\d{2,5})(?::(?P<target>\d{1,5})(?:/\w+)?)?$"
)
VARIANT_TOKEN_RE = re.compile(r"v\d+$", re.IGNORECASE)

ENV_BINDING_SERVICE_ALIASES = {
    "frontend": "frontend",
    "backend": "api",
    "api": "api",
    "web": "web",
    "gui": "gui",
    "desktop": "desktop",
    "app": "app",
    "db": "db",
    "database": "db",
    "postgres": "db",
    "postgresql": "db",
    "timescaledb": "db",
    "redis": "redis",
    "monitor": "monitor",
    "worker": "worker",
    "hmr": "hmr",
}
CANONICAL_BINDING_SERVICE_ALIASES = {
    "app": "api",
    "backend": "api",
    "postgres": "db",
    "postgresql": "db",
    "database": "db",
    "timescaledb": "db",
}
CANONICAL_BINDING_BASES = {"frontend", "web", "gui", "desktop", "api", "db", "redis", "monitor", "worker"}
ALIAS_ONLY_SCRIPT_TOKENS = {"dev", "preview", "start", "serve"}
ENV_REFERENCE_TOKENS = {"smtp", "imap", "pop", "mail", "oauth", "callback", "llm", "lmstudio", "ollama"}
ENV_FILE_PRIORITY = {
    ".env.local": 0,
    ".env.development": 1,
    ".env": 2,
    ".env.example": 3,
}
GOVERNING_SERVICE_STATUSES = {"active", "external"}


def _is_ignored(path: Path) -> bool:
    return any(part in IGNORED_DIRS for part in path.parts)


def iter_scan_files(project_path: Path) -> list[Path]:
    files: list[Path] = []
    for current_root, dir_names, file_names in os.walk(project_path, topdown=True):
        dir_names[:] = [name for name in dir_names if name not in IGNORED_DIRS and not name.startswith(".")]
        root_path = Path(current_root)
        for file_name in file_names:
            if file_name in SCAN_FILE_NAMES:
                files.append(root_path / file_name)
    return _filter_preferred_env_files(sorted(files))


def _filter_preferred_env_files(files: list[Path]) -> list[Path]:
    by_parent: dict[Path, list[Path]] = {}
    for path in files:
        by_parent.setdefault(path.parent, []).append(path)

    selected: list[Path] = []
    for directory, candidates in by_parent.items():
        env_candidates = [path for path in candidates if path.name.startswith(".env")]
        if env_candidates:
            keep_env = min(env_candidates, key=lambda path: (ENV_FILE_PRIORITY.get(path.name, 99), path.name))
            selected.append(keep_env)
        selected.extend(path for path in candidates if not path.name.startswith(".env"))
    return sorted(selected)


def _guess_service_name(path: Path, fallback: str) -> str:
    for part in reversed(path.parts[:-1]):
        lowered = part.lower()
        if lowered in {"frontend", "backend", "web", "api", "gui", "desktop", "monitor", "mcp-server"}:
            return lowered.replace("mcp-server", "monitor")
    return fallback


def _kind_for_service(service: str) -> str:
    lowered = service.lower()
    if lowered.endswith("-hmr"):
        return "other"
    tokens = [token for token in re.split(r"[-_]", lowered) if token]
    if any(token in {"frontend", "web", "gui", "desktop"} for token in tokens):
        return "web"
    if any(token in {"backend", "api", "app"} for token in tokens):
        return "api"
    if "monitor" in tokens:
        return "web"
    if "redis" in tokens:
        return "redis"
    if any(token in {"db", "postgres", "postgresql", "timescaledb", "database"} for token in tokens):
        return "db"
    return "other"


def _extract_port_value(raw_value: str) -> int | None:
    value = raw_value.strip()
    if value.isdigit():
        return int(value)
    env_match = ENV_FALLBACK_PORT_RE.search(value)
    if env_match:
        return int(env_match.group("port"))
    return None


def _service_from_env_suffix(suffix: str) -> str:
    normalized = suffix.lower().strip("_")
    if normalized.endswith("_hmr"):
        prefix = normalized.removesuffix("_hmr")
        prefix_service = _service_from_env_suffix(prefix) if prefix else ""
        return f"{prefix_service}-hmr" if prefix_service else "hmr"
    for alias, service in ENV_BINDING_SERVICE_ALIASES.items():
        if normalized == alias or normalized.endswith(f"_{alias}"):
            return service
    return normalized.replace("_", "-")


def _kind_from_env_suffix(suffix: str) -> str:
    service = _service_from_env_suffix(suffix)
    return _kind_for_service(service)


def _variant_from_path(project_root: Path, path: Path) -> str | None:
    try:
        relative = path.relative_to(project_root)
    except ValueError:
        relative = path
    for part in relative.parts[:-1]:
        lowered = part.lower()
        if VARIANT_TOKEN_RE.fullmatch(lowered):
            return lowered
    return None


def _canonical_binding_service_name(project_root: Path, path: Path, service: str, kind: str) -> str:
    lowered = service.lower().strip()
    if lowered.endswith("-hmr"):
        prefix = _canonical_binding_service_name(project_root, path, lowered.removesuffix("-hmr"), kind)
        return f"{prefix}-hmr"

    if lowered in CANONICAL_BINDING_SERVICE_ALIASES:
        return CANONICAL_BINDING_SERVICE_ALIASES[lowered]

    tokens = [token for token in re.split(r"[-_]", lowered) if token]
    variant = next((token for token in tokens if VARIANT_TOKEN_RE.fullmatch(token)), _variant_from_path(project_root, path))
    canonical_tokens: list[str] = []
    for token in tokens:
        if token in ALIAS_ONLY_SCRIPT_TOKENS or VARIANT_TOKEN_RE.fullmatch(token):
            continue
        canonical = CANONICAL_BINDING_SERVICE_ALIASES.get(token, token)
        if canonical in CANONICAL_BINDING_BASES:
            canonical_tokens.append(canonical)

    if not canonical_tokens:
        return lowered

    base = canonical_tokens[-1]
    if variant and base in {"frontend", "web", "gui", "desktop", "api"}:
        return f"{variant}-{base}"
    return base


def _classify_env_port_key(project_root: Path, path: Path, key: str) -> tuple[str, str, str] | None:
    if key == "PORT":
        service = _guess_service_name(path.relative_to(project_root), "app")
        if service == "app":
            service = "api"
        else:
            service = _canonical_binding_service_name(project_root, path, service, _kind_for_service(service))
        kind = _kind_for_service(service)
        return ("binding", service, kind)
    if not key.endswith("_PORT"):
        return None

    suffix = key[:-5]
    tokens = suffix.lower().split("_")
    if any(token in ENV_REFERENCE_TOKENS for token in tokens):
        service = suffix.lower()
        return ("reference", service, "reference")
    if any(token in ENV_BINDING_SERVICE_ALIASES for token in tokens):
        service = _service_from_env_suffix(suffix)
        return ("binding", service, _kind_from_env_suffix(suffix))
    return ("reference", suffix.lower(), "reference")


def _resolve_vite_port_token(token: str, variable_ports: dict[str, tuple[str, int]]) -> tuple[str | None, int | None]:
    cleaned = token.strip()
    if cleaned.isdigit():
        return (None, int(cleaned))
    return variable_ports.get(cleaned, (None, None))


def _discover_package_json(project_root: Path, path: Path) -> list[DiscoveredPort]:
    items: list[DiscoveredPort] = []
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError:
        return items
    scripts = payload.get("scripts", {})
    base_service = _guess_service_name(path.relative_to(project_root), "app")
    for script_name, command in scripts.items():
        for pattern, service_name, kind in (
            (NEXT_PORT_RE, "web", "web"),
            (VITE_SCRIPT_PORT_RE, base_service if base_service != "app" else "web", "web"),
            (UVICORN_PORT_RE, "api", "api"),
        ):
            match = pattern.search(command)
            if not match:
                continue
            port = _extract_port_value(match.group("value"))
            if port is None:
                continue
            items.append(
                DiscoveredPort(
                    project=str(project_root),
                    source_file=str(path),
                    port=port,
                    role="binding",
                    service=service_name if script_name == "dev" else f"{service_name}-{script_name.replace(':', '-')}",
                    kind=kind,
                    detail=f"package.json script {script_name}",
                )
            )
    return items


def _discover_vite_config(project_root: Path, path: Path) -> list[DiscoveredPort]:
    text = path.read_text(errors="ignore")
    variable_ports = {
        match.group("name"): (match.group("env"), int(match.group("port")))
        for match in JS_ENV_PORT_ASSIGN_RE.finditer(text)
    }
    items: list[DiscoveredPort] = []

    match = SERVER_PORT_TOKEN_RE.search(text)
    if match:
        env_key, port = _resolve_vite_port_token(match.group("token"), variable_ports)
        if port is not None:
            service = _service_from_env_suffix(env_key.removeprefix("PM_PORT_")) if env_key and env_key.startswith("PM_PORT_") else _guess_service_name(path.relative_to(project_root), "web")
            items.append(
                DiscoveredPort(
                    project=str(project_root),
                    source_file=str(path),
                    port=port,
                    role="binding",
                    service=service,
                    kind=_kind_for_service(service),
                    detail="vite.config server.port",
                )
            )

    hmr_match = HMR_PORT_TOKEN_RE.search(text)
    if hmr_match:
        env_key, port = _resolve_vite_port_token(hmr_match.group("token"), variable_ports)
        if port is not None:
            service = _service_from_env_suffix(env_key.removeprefix("PM_PORT_")) if env_key and env_key.startswith("PM_PORT_") else f"{_guess_service_name(path.relative_to(project_root), 'web')}-hmr"
            items.append(
                DiscoveredPort(
                    project=str(project_root),
                    source_file=str(path),
                    port=port,
                    role="binding",
                    service=service,
                    kind=_kind_for_service(service),
                    detail="vite.config server.hmr.port",
                )
            )
    return items


def _parse_compose_mapping(value: str) -> tuple[str, int] | None:
    raw = value.strip().strip('"').strip("'")
    raw = re.sub(r"/\w+$", "", raw)
    segments: list[str] = []
    current: list[str] = []
    brace_depth = 0
    for char in raw:
        if char == "{" and current and current[-1] == "$":
            brace_depth += 1
        elif char == "}" and brace_depth:
            brace_depth -= 1
        elif char == ":" and brace_depth == 0:
            segments.append("".join(current))
            current = []
            continue
        current.append(char)
    segments.append("".join(current))

    if len(segments) == 1:
        bind_host = "0.0.0.0"
        published_token = segments[0]
    elif len(segments) == 2:
        bind_host = "0.0.0.0"
        published_token = segments[0]
    elif len(segments) == 3:
        bind_host = segments[0] or "0.0.0.0"
        published_token = segments[1]
    else:
        match = COMPOSE_PORT_MAPPING_RE.match(raw)
        if not match:
            return None
        bind_host = match.group("bind_host") or "0.0.0.0"
        published_token = match.group("published")

    published = _extract_port_value(published_token)
    if published is None:
        return None
    if bind_host.startswith("${"):
        bind_host = "0.0.0.0"
    return bind_host, published


def _extract_compose_published_port(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return _extract_port_value(value)
    return None


def _discover_compose(project_root: Path, path: Path) -> list[DiscoveredPort]:
    text = path.read_text(errors="ignore")
    try:
        payload = yaml.safe_load(text) or {}
    except yaml.YAMLError:
        return []
    items: list[DiscoveredPort] = []
    services = payload.get("services", {})
    for service_name, service_config in services.items():
        ports = service_config.get("ports", [])
        for port_mapping in ports:
            if isinstance(port_mapping, str):
                parsed = _parse_compose_mapping(port_mapping)
                if parsed is None:
                    continue
                bind_host, host_port = parsed
            elif isinstance(port_mapping, dict):
                published = _extract_compose_published_port(port_mapping.get("published"))
                host_ip = port_mapping.get("host_ip", "0.0.0.0")
                if published is None:
                    continue
                bind_host = host_ip
                host_port = published
            else:
                continue
            lowered = service_name.lower()
            if "redis" in lowered:
                kind = "redis"
            elif any(token in lowered for token in {"db", "postgres", "timescaledb"}):
                kind = "db"
            elif lowered in {"frontend", "web"}:
                kind = "web"
            elif lowered in {"backend", "api"}:
                kind = "api"
            else:
                kind = _kind_for_service(lowered)
            items.append(
                DiscoveredPort(
                    project=str(project_root),
                    source_file=str(path),
                    port=host_port,
                    role="binding",
                    service=lowered,
                    kind=kind,
                    detail=f"compose service {service_name}",
                    bind_host=bind_host,
                )
            )
    return items


def _discover_env(project_root: Path, path: Path) -> list[DiscoveredPort]:
    items: list[DiscoveredPort] = []
    for line in path.read_text(errors="ignore").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        match = PORT_KEY_RE.match(stripped)
        if not match:
            continue
        key = match.group("key")
        value = match.group("value").strip().strip('"').strip("'")
        classification = _classify_env_port_key(project_root, path, key)
        port = _extract_port_value(value)
        if classification and port is not None:
            role, service, kind = classification
            items.append(
                DiscoveredPort(
                    project=str(project_root),
                    source_file=str(path),
                    port=port,
                    role=role,
                    service=service,
                    kind=kind,
                    detail=f"{key} in {path.name}",
                )
            )
            continue
        for url_match in URL_PORT_RE.finditer(value):
            items.append(
                DiscoveredPort(
                    project=str(project_root),
                    source_file=str(path),
                    port=int(url_match.group("port")),
                    role="reference",
                    service=key.lower(),
                    kind="reference",
                    detail=f"{key} -> {value}",
                )
            )
    return items


def discover_source_ports(project_root: Path, path: Path) -> list[DiscoveredPort]:
    if path.name == "package.json":
        return _discover_package_json(project_root, path)
    if path.name.startswith("vite.config"):
        return _discover_vite_config(project_root, path)
    if path.name in {"docker-compose.yml", "docker-compose.yaml", "compose.yaml"}:
        return _discover_compose(project_root, path)
    if path.name.startswith(".env"):
        return _discover_env(project_root, path)
    return []


def _source_priority(path: str) -> tuple[int, int, str]:
    source = Path(path)
    name = source.name
    if name.startswith(".env"):
        return (ENV_FILE_PRIORITY.get(name, 99), len(source.parts), str(source))
    if name.endswith(".ts"):
        return (0, len(source.parts), str(source))
    if name.endswith(".js"):
        return (1, len(source.parts), str(source))
    return (10, len(source.parts), str(source))


def _binding_registry_lookup(registry: Registry | None, project_root: Path) -> dict[int, tuple[str, str, str]]:
    if registry is None:
        return {}
    lookup: dict[int, tuple[str, str, str]] = {}
    for service in registry.services_for_project(project_root):
        if service.status not in GOVERNING_SERVICE_STATUSES:
            continue
        lookup[service.port] = (service.service, service.kind, service.source_file)
    return lookup


def discover_project_ports(project_root: Path, registry: Registry | None = None) -> list[DiscoveredPort]:
    items: list[DiscoveredPort] = []
    for path in iter_scan_files(project_root):
        items.extend(discover_source_ports(project_root, path))
    registry_bindings = _binding_registry_lookup(registry, project_root)
    unique: dict[tuple[object, ...], DiscoveredPort] = {}
    for item in items:
        if item.role == "binding":
            registry_binding = registry_bindings.get(item.port)
            if registry_binding is not None:
                canonical_service, canonical_kind, preferred_source = registry_binding
            else:
                canonical_service = _canonical_binding_service_name(project_root, Path(item.source_file), item.service, item.kind)
                canonical_kind = _kind_for_service(canonical_service)
                preferred_source = ""
            key = (item.role, canonical_service, canonical_kind, item.port, item.bind_host)
            existing = unique.get(key)
            if existing is None:
                unique[key] = DiscoveredPort(
                    project=item.project,
                    source_file=item.source_file,
                    port=item.port,
                    role=item.role,
                    service=canonical_service,
                    kind=canonical_kind,
                    detail=item.detail,
                    bind_host=item.bind_host,
                    aliases=[] if item.service == canonical_service else [item.service],
                    source_files=[item.source_file],
                    details=[item.detail] if item.detail else [],
                )
                continue
            if item.service != canonical_service and item.service not in existing.aliases:
                existing.aliases.append(item.service)
            if item.source_file not in existing.source_files:
                existing.source_files.append(item.source_file)
            if item.detail and item.detail not in existing.details:
                existing.details.append(item.detail)
            if preferred_source and preferred_source in existing.source_files:
                existing.source_file = preferred_source
            elif _source_priority(item.source_file) < _source_priority(existing.source_file):
                existing.source_file = item.source_file
                existing.detail = item.detail
            continue
        key = (item.source_file, item.port, item.role, item.service, item.detail)
        unique[key] = DiscoveredPort(
            project=item.project,
            source_file=item.source_file,
            port=item.port,
            role=item.role,
            service=item.service,
            kind=item.kind,
            detail=item.detail,
            bind_host=item.bind_host,
            source_files=[item.source_file],
            details=[item.detail] if item.detail else [],
        )
    return sorted(unique.values(), key=lambda item: (item.port, item.role, item.source_file, item.service))


def discover_all(registry: Registry) -> dict[Path, list[DiscoveredPort]]:
    from .registry import configured_project_paths

    output: dict[Path, list[DiscoveredPort]] = {}
    for project in configured_project_paths(registry):
        output[project] = discover_project_ports(project, registry)
    return output
