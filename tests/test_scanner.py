from __future__ import annotations

import json
from pathlib import Path

from portmanager.models import Registry, ServiceEntry
from portmanager.scanner import discover_project_ports


def test_discover_project_ports_handles_env_wired_configs_and_references(tmp_path: Path) -> None:
    project = tmp_path / "demo"
    project.mkdir()
    (project / "package.json").write_text(
        json.dumps(
            {
                "scripts": {
                    "dev": "next dev --port ${PM_PORT_WEB:-5200}",
                    "dev:api": "python3 -m uvicorn app.main:app --reload --port ${PM_PORT_API:-5201}",
                }
            }
        )
    )
    (project / "vite.config.ts").write_text(
        "\n".join(
            [
                "const webPort = Number(process.env.PM_PORT_WEB ?? 5202);",
                "const apiPort = Number(process.env.PM_PORT_API ?? 5201);",
                "export default {",
                "  server: {",
                "    port: webPort,",
                "    proxy: { '/api': { target: `http://localhost:${apiPort}` } },",
                "  },",
                "};",
            ]
        )
    )
    (project / ".env").write_text(
        "\n".join(
            [
                "PORT=5203",
                "STAYZERO_API_PORT=5212",
                "EMAIL_SMTP_PORT=587",
                "EMAIL_IMAP_PORT=993",
                "LOCAL_LLM_BASE_URL=http://localhost:1234/v1",
                "REDIS_URL=redis://localhost:5217",
                "",
            ]
        )
    )

    ports = discover_project_ports(project)

    bindings = {(item.port, item.service, item.role) for item in ports if item.role == "binding"}
    references = {(item.port, item.service, item.role) for item in ports if item.role != "binding"}

    assert (5200, "web", "binding") in bindings
    assert (5201, "api", "binding") in bindings
    assert (5202, "web", "binding") in bindings
    assert (5203, "api", "binding") in bindings
    assert (5212, "api", "binding") in bindings
    assert (587, "email_smtp", "reference") in references
    assert (993, "email_imap", "reference") in references
    assert (1234, "local_llm_base_url", "reference") in references
    assert (5217, "redis_url", "reference") in references


def test_discover_project_ports_prefers_real_env_and_dedupes_duplicate_bindings(tmp_path: Path) -> None:
    project = tmp_path / "demo"
    project.mkdir()
    (project / ".env").write_text("PORT=5230\n")
    (project / ".env.example").write_text("PORT=3000\n")
    (project / "vite.config.js").write_text("export default { server: { port: 5225 } }")
    (project / "vite.config.ts").write_text("export default { server: { port: 5225 } }")

    ports = discover_project_ports(project)

    env_bindings = [item for item in ports if item.port == 5230]
    vite_bindings = [item for item in ports if item.port == 5225]

    assert len(env_bindings) == 1
    assert env_bindings[0].service == "api"
    assert env_bindings[0].source_file.endswith("/.env")
    assert len(vite_bindings) == 1
    assert vite_bindings[0].source_file.endswith("/vite.config.ts")


def test_discover_project_ports_collapses_alias_only_duplicates_with_registry_topology(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    project = workspace / "demo"
    frontend = project / "frontend"
    v2_frontend = project / "v2" / "frontend"
    frontend.mkdir(parents=True)
    v2_frontend.mkdir(parents=True)
    (frontend / "package.json").write_text(json.dumps({"scripts": {"preview": "vite preview --port ${PM_PORT_FRONTEND:-5201}"}}))
    (frontend / "vite.config.ts").write_text("export default { server: { port: 5201 } }")
    (v2_frontend / "package.json").write_text(json.dumps({"scripts": {"preview": "vite preview --port ${PM_PORT_V2_FRONTEND:-5203}"}}))
    (v2_frontend / "vite.config.ts").write_text("export default { server: { port: 5203 } }")
    (project / "package.json").write_text(
        json.dumps(
            {
                "scripts": {
                    "dev": "python -m uvicorn app.main:app --port ${PM_PORT_API:-5202}",
                    "dev:backend": "python -m uvicorn app.main:app --port ${PM_PORT_API:-5202}",
                    "dev:v2": "python -m uvicorn app.main:app --port ${PM_PORT_V2_API:-5204}",
                    "dev:v2:backend": "python -m uvicorn app.main:app --port ${PM_PORT_V2_API:-5204}",
                }
            }
        )
    )
    registry = Registry(
        services=[
            ServiceEntry(project=str(project), status="active", service="frontend", kind="web", port=5201, bind_host="127.0.0.1", source_file=str(frontend / "vite.config.ts")),
            ServiceEntry(project=str(project), status="active", service="api", kind="api", port=5202, bind_host="127.0.0.1", source_file=str(project / "package.json")),
            ServiceEntry(project=str(project), status="active", service="v2-frontend", kind="web", port=5203, bind_host="127.0.0.1", source_file=str(v2_frontend / "vite.config.ts")),
            ServiceEntry(project=str(project), status="active", service="v2-api", kind="api", port=5204, bind_host="127.0.0.1", source_file=str(project / "package.json")),
        ]
    )

    ports = [item for item in discover_project_ports(project, registry) if item.role == "binding"]

    assert [(item.port, item.service) for item in ports] == [
        (5201, "frontend"),
        (5202, "api"),
        (5203, "v2-frontend"),
        (5204, "v2-api"),
    ]
    assert ports[0].aliases == ["frontend-preview"]
    assert ports[1].aliases == ["api-dev-backend"]
    assert set(ports[2].aliases) == {"frontend", "frontend-preview"}
    assert set(ports[3].aliases) == {"api-dev-v2", "api-dev-v2-backend"}


def test_discover_project_ports_finds_nested_compose_bindings_and_prefers_registry_source(tmp_path: Path) -> None:
    project = tmp_path / "demo"
    project.mkdir()
    compose_dir = project / "infra" / "docker"
    compose_dir.mkdir(parents=True)
    (project / "docker-compose.yml").write_text(
        "\n".join(
            [
                "services:",
                "  postgres:",
                "    ports:",
                "      - \"${PM_PORT_DB:-5216}:5432\"",
                "",
            ]
        )
    )
    (compose_dir / "docker-compose.yml").write_text(
        "\n".join(
            [
                "services:",
                "  postgres:",
                "    ports:",
                "      - \"${PM_PORT_DB:-5216}:5432\"",
                "  redis:",
                "    ports:",
                "      - \"127.0.0.1:${PM_PORT_REDIS:-5217}:6379\"",
                "",
            ]
        )
    )
    registry = Registry(
        services=[
            ServiceEntry(project=str(project), status="active", service="db", kind="db", port=5216, bind_host="127.0.0.1", source_file=str(compose_dir / "docker-compose.yml")),
            ServiceEntry(project=str(project), status="active", service="redis", kind="redis", port=5217, bind_host="127.0.0.1", source_file=str(compose_dir / "docker-compose.yml")),
        ]
    )

    ports = [item for item in discover_project_ports(project, registry) if item.role == "binding"]

    assert {(item.port, item.service, item.kind, item.bind_host) for item in ports} == {
        (5216, "db", "db", "0.0.0.0"),
        (5217, "redis", "redis", "127.0.0.1"),
    }
    assert all(item.source_file.endswith("/infra/docker/docker-compose.yml") for item in ports)


def test_discover_project_ports_finds_conditional_hmr_port(tmp_path: Path) -> None:
    project = tmp_path / "demo"
    project.mkdir()
    (project / "vite.config.ts").write_text(
        "\n".join(
            [
                "const host = process.env.TAURI_DEV_HOST;",
                "const webPort = Number(process.env.PM_PORT_WEB ?? 5210);",
                "const hmrPort = Number(process.env.PM_PORT_WEB_HMR ?? 5211);",
                "export default {",
                "  server: {",
                "    port: webPort,",
                "    hmr: host ? {",
                "      protocol: 'ws',",
                "      host,",
                "      port: hmrPort,",
                "    } : undefined,",
                "  },",
                "};",
            ]
        )
    )

    ports = discover_project_ports(project)

    bindings = {(item.port, item.service, item.kind) for item in ports if item.role == "binding"}
    assert (5210, "web", "web") in bindings
    assert (5211, "web-hmr", "other") in bindings
