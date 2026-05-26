from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path


def normalize_service_key(value: str) -> str:
    cleaned = []
    for char in value.strip():
        cleaned.append(char if char.isalnum() else "_")
    return "".join(cleaned).strip("_").upper() or "SERVICE"


@dataclass(slots=True)
class RootEntry:
    path: str

    @property
    def path_obj(self) -> Path:
        return Path(self.path).expanduser().resolve()

    def to_dict(self) -> dict[str, object]:
        return {"path": self.path}


@dataclass(slots=True)
class ProjectEntry:
    path: str
    status: str = "active"
    notes: str = ""

    @property
    def path_obj(self) -> Path:
        return Path(self.path).expanduser().resolve()

    def to_dict(self) -> dict[str, object]:
        return {"path": self.path, "status": self.status, "notes": self.notes}


@dataclass(slots=True)
class ServiceEntry:
    project: str
    status: str
    service: str
    kind: str
    port: int
    bind_host: str
    source_file: str = ""
    notes: str = ""

    @property
    def project_path(self) -> Path:
        return Path(self.project).expanduser().resolve()

    @property
    def source_path(self) -> Path | None:
        if not self.source_file:
            return None
        source = Path(self.source_file).expanduser()
        if source.is_absolute():
            return source.resolve()
        return (self.project_path / source).resolve()

    @property
    def env_key(self) -> str:
        return normalize_service_key(self.service)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class Registry:
    version: int = 1
    managed_range_start: int = 5190
    managed_range_end: int = 5299
    roots: list[RootEntry] = field(default_factory=list)
    projects: list[ProjectEntry] = field(default_factory=list)
    services: list[ServiceEntry] = field(default_factory=list)

    def active_ports(self) -> set[int]:
        return {service.port for service in self.services if service.status == "active"}

    def service_for(self, project: Path, service_name: str) -> ServiceEntry | None:
        target_project = project.expanduser().resolve()
        for service in self.services:
            if service.project_path == target_project and service.service == service_name:
                return service
        return None

    def services_for_project(self, project: Path) -> list[ServiceEntry]:
        target_project = project.expanduser().resolve()
        return sorted(
            [service for service in self.services if service.project_path == target_project],
            key=lambda item: (item.port, item.service),
        )

    def configured_projects(self) -> list[ProjectEntry]:
        return sorted(self.projects, key=lambda item: item.path)


@dataclass(slots=True)
class DiscoveredPort:
    project: str
    source_file: str
    port: int
    role: str
    service: str
    kind: str
    detail: str = ""
    bind_host: str = "127.0.0.1"
    aliases: list[str] = field(default_factory=list)
    source_files: list[str] = field(default_factory=list)
    details: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class Listener:
    port: int
    process: str
    raw: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
