from __future__ import annotations

import json
from pathlib import Path

import portmanager.registry as registry_module
from portmanager.models import Listener, Registry, RootEntry, ServiceEntry
from portmanager.registry import build_scan_payload, next_free_port, write_project_sync_files


def test_next_free_port_skips_assigned_and_listeners() -> None:
    registry = Registry(
        managed_range_start=5190,
        managed_range_end=5195,
        services=[
            ServiceEntry(
                project="/tmp/demo",
                status="active",
                service="web",
                kind="web",
                port=5190,
                bind_host="127.0.0.1",
            )
        ],
    )
    listeners = {5191: [Listener(port=5191, process="python", raw="python ...")]}

    assert next_free_port(registry, listeners) == 5192


def test_write_project_sync_files_generates_env_and_json(tmp_path: Path) -> None:
    project = tmp_path / "demo"
    project.mkdir()
    registry = Registry(
        services=[
            ServiceEntry(
                project=str(project),
                status="active",
                service="api",
                kind="api",
                port=5209,
                bind_host="127.0.0.1",
                source_file=str(project / "package.json"),
            ),
            ServiceEntry(
                project=str(project),
                status="active",
                service="redis",
                kind="redis",
                port=5217,
                bind_host="127.0.0.1",
            ),
        ]
    )

    env_path, json_path = write_project_sync_files(registry, project)

    env_text = env_path.read_text()
    assert "PM_PORT_API=5209" in env_text
    assert "PM_URL_API=http://127.0.0.1:5209" in env_text
    assert "PM_PORT_REDIS=5217" in env_text
    assert "PM_URL_REDIS=redis://127.0.0.1:5217" in env_text

    payload = json.loads(json_path.read_text())
    assert payload["project"] == str(project.resolve())
    assert [item["service"] for item in payload["services"]] == ["api", "redis"]


def test_build_scan_payload_classifies_projects_and_reports_registry_only_services(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    active = workspace / "active"
    archived = workspace / "!DEPRECATED"
    idle = workspace / "idle"
    active.mkdir(parents=True)
    archived.mkdir(parents=True)
    idle.mkdir(parents=True)
    (active / "vite.config.ts").write_text("export default { server: { port: 5200 } }")
    (archived / "vite.config.ts").write_text("export default { server: { port: 3000 } }")

    registry = Registry(
        roots=[RootEntry(str(workspace))],
        services=[
            ServiceEntry(
                project=str(active),
                status="active",
                service="web",
                kind="web",
                port=5200,
                bind_host="127.0.0.1",
                source_file=str(active / "vite.config.ts"),
            ),
            ServiceEntry(
                project=str(active),
                status="active",
                service="monitor",
                kind="web",
                port=5201,
                bind_host="127.0.0.1",
                source_file=str(active / "monitor.py"),
            ),
        ],
    )
    monkeypatch.setattr(registry_module, "load_listeners", lambda: {})

    payload = build_scan_payload(registry, listeners={})

    active_info = payload["projects"][str(active)]
    archived_info = payload["projects"][str(archived)]
    idle_info = payload["projects"][str(idle)]

    assert active_info["classification"] == "active_app"
    assert active_info["summary"]["governed_port_count"] == 2
    assert active_info["summary"]["registered_only_count"] == 1
    assert active_info["summary"]["unmanaged_count"] == 0
    assert active_info["registered_only_services"][0]["service"] == "monitor"
    assert archived_info["classification"] == "archived"
    assert idle_info["classification"] == "non_app"


def test_validate_registry_accepts_parser_aware_managed_binding(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    project = workspace / "demo"
    project.mkdir(parents=True)
    package_json = project / "package.json"
    package_json.write_text(json.dumps({"scripts": {"dev": "next dev --port ${PM_PORT_WEB:-5200}"}}))

    registry = Registry(
        roots=[RootEntry(str(workspace))],
        services=[
            ServiceEntry(
                project=str(project),
                status="active",
                service="web",
                kind="web",
                port=5200,
                bind_host="127.0.0.1",
                source_file=str(package_json),
            )
        ],
    )
    monkeypatch.setattr(registry_module, "load_listeners", lambda: {})

    errors = registry_module.validate_registry(registry)

    assert errors == []


def test_validate_registry_accepts_external_out_of_range_binding(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    project = workspace / "demo"
    project.mkdir(parents=True)
    compose = project / "docker-compose.yml"
    compose.write_text(
        "\n".join(
            [
                "services:",
                "  pocketbase:",
                "    image: ghcr.io/example/pocketbase",
                "    ports:",
                '      - "8090:8080"',
                "",
            ]
        )
    )

    registry = Registry(
        managed_range_start=5190,
        managed_range_end=5299,
        roots=[RootEntry(str(workspace))],
        services=[
            ServiceEntry(
                project=str(project),
                status="external",
                service="pocketbase",
                kind="api",
                port=8090,
                bind_host="127.0.0.1",
                source_file=str(compose),
            )
        ],
    )
    monkeypatch.setattr(registry_module, "load_listeners", lambda: {})

    errors = registry_module.validate_registry(registry)

    assert errors == []


def test_build_scan_payload_counts_external_binding_as_governed(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    project = workspace / "demo"
    project.mkdir(parents=True)
    compose = project / "docker-compose.yml"
    compose.write_text(
        "\n".join(
            [
                "services:",
                "  pocketbase:",
                "    image: ghcr.io/example/pocketbase",
                "    ports:",
                '      - "8090:8080"',
                "",
            ]
        )
    )

    registry = Registry(
        roots=[RootEntry(str(workspace))],
        services=[
            ServiceEntry(
                project=str(project),
                status="external",
                service="pocketbase",
                kind="api",
                port=8090,
                bind_host="127.0.0.1",
                source_file=str(compose),
            )
        ],
    )

    payload = build_scan_payload(registry, listeners={})

    project_info = payload["projects"][str(project)]
    assert project_info["classification"] == "active_app"
    assert project_info["summary"]["governed_port_count"] == 1
    assert project_info["summary"]["unmanaged_count"] == 0
    assert project_info["bindings"][0]["service"] == "pocketbase"
    assert project_info["bindings"][0]["kind"] == "api"


def test_validate_registry_resolves_relative_source_file_from_project(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    project = workspace / "demo"
    project.mkdir(parents=True)
    (project / "vite.config.ts").write_text("export default { server: { port: 5200 } }")

    registry = Registry(
        roots=[RootEntry(str(workspace))],
        services=[
            ServiceEntry(
                project=str(project),
                status="active",
                service="web",
                kind="web",
                port=5200,
                bind_host="127.0.0.1",
                source_file="vite.config.ts",
            )
        ],
    )
    monkeypatch.setattr(registry_module, "load_listeners", lambda: {})

    errors = registry_module.validate_registry(registry)

    assert errors == []


def test_validate_registry_rejects_stale_literal_with_matching_number_elsewhere(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    project = workspace / "demo"
    project.mkdir(parents=True)
    vite_config = project / "vite.config.ts"
    vite_config.write_text(
        "\n".join(
            [
                "// historical port 5200",
                "export default {",
                "  server: {",
                "    port: 3000,",
                "  },",
                "};",
            ]
        )
    )

    registry = Registry(
        roots=[RootEntry(str(workspace))],
        services=[
            ServiceEntry(
                project=str(project),
                status="active",
                service="web",
                kind="web",
                port=5200,
                bind_host="127.0.0.1",
                source_file=str(vite_config),
            )
        ],
    )
    monkeypatch.setattr(registry_module, "load_listeners", lambda: {})

    errors = registry_module.validate_registry(registry)

    assert any(error.code == "source_drift" and "source file drift" in error.message for error in errors)


def test_validate_registry_ignores_reference_only_ports(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    project = workspace / "demo"
    project.mkdir(parents=True)
    (project / ".env.example").write_text(
        "\n".join(
            [
                "EMAIL_SMTP_PORT=587",
                "EMAIL_IMAP_PORT=993",
                "LOCAL_LLM_BASE_URL=http://localhost:1234/v1",
                "",
            ]
        )
    )

    registry = Registry(roots=[RootEntry(str(workspace))], services=[])
    monkeypatch.setattr(registry_module, "load_listeners", lambda: {})

    errors = registry_module.validate_registry(registry)

    assert errors == []
