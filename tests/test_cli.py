from __future__ import annotations

import json
from pathlib import Path

import portmanager.cli as cli_module
import portmanager.registry as registry_module
from portmanager.cli import main


def test_init_creates_workspace_registry_and_generated_artifacts(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(registry_module, "load_listeners", lambda: {})

    result = main(["init"])

    assert result == 0
    assert (tmp_path / "ports.toml").exists()
    assert (tmp_path / "ports.lock.json").exists()
    assert (tmp_path / "PORTS.md").exists()
    assert f'path = "{tmp_path}"' in (tmp_path / "ports.toml").read_text()


def test_claim_refuses_missing_registry(tmp_path: Path, capsys, monkeypatch) -> None:
    registry_path = tmp_path / "ports.toml"
    project = tmp_path / "demo"
    project.mkdir()
    monkeypatch.setattr(registry_module, "load_listeners", lambda: {})

    result = main(["--registry", str(registry_path), "claim", str(project), "web", "--kind", "web", "--dry-run"])

    captured = capsys.readouterr()
    assert result == 1
    assert "registry not found" in captured.err
    assert not registry_path.exists()


def test_claim_refuses_project_outside_registry_roots(tmp_path: Path, capsys, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outsider = tmp_path / "elsewhere" / "demo"
    outsider.mkdir(parents=True)
    registry_path = tmp_path / "ports.toml"
    monkeypatch.setattr(registry_module, "load_listeners", lambda: {})

    assert main(["--registry", str(registry_path), "init", "--root", str(workspace)]) == 0
    capsys.readouterr()
    result = main(["--registry", str(registry_path), "claim", str(outsider), "web", "--kind", "web"])

    captured = capsys.readouterr()
    assert result == 1
    assert "is not under any root" in captured.err
    assert "[[services]]" not in registry_path.read_text()


def test_claim_refuses_explicit_port_registered_to_other_project(tmp_path: Path, capsys, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    first = workspace / "first"
    second = workspace / "second"
    first.mkdir(parents=True)
    second.mkdir()
    registry_path = tmp_path / "ports.toml"
    monkeypatch.setattr(registry_module, "load_listeners", lambda: {})

    assert main(["--registry", str(registry_path), "init", "--root", str(workspace)]) == 0
    assert main(["--registry", str(registry_path), "claim", str(first), "web", "--kind", "web", "--port", "5195", "--adopt-existing"]) == 0
    capsys.readouterr()
    result = main(["--registry", str(registry_path), "claim", str(second), "web", "--kind", "web", "--port", "5195", "--adopt-existing"])

    captured = capsys.readouterr()
    assert result == 1
    assert "already registered" in captured.err
    assert f'project = "{second}"' not in registry_path.read_text()


def test_claim_auto_assign_skips_registered_live_and_unbindable_ports(tmp_path: Path, capsys, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    first = workspace / "first"
    second = workspace / "second"
    first.mkdir(parents=True)
    second.mkdir()
    registry_path = tmp_path / "ports.toml"
    listener = registry_module.Listener(port=5191, process="python", raw="python ... TCP 127.0.0.1:5191 (LISTEN)")
    monkeypatch.setattr(registry_module, "load_listeners", lambda: {5191: [listener]})
    monkeypatch.setattr(cli_module, "load_listeners", lambda: {5191: [listener]})
    monkeypatch.setattr(registry_module, "port_is_bindable", lambda port, host="127.0.0.1": port != 5192)

    assert main(["--registry", str(registry_path), "init", "--root", str(workspace)]) == 0
    assert main(["--registry", str(registry_path), "claim", str(first), "web", "--kind", "web", "--port", "5190", "--adopt-existing"]) == 0
    capsys.readouterr()
    result = main(["--registry", str(registry_path), "claim", str(second), "web", "--kind", "web"])

    output = capsys.readouterr().out
    assert result == 0
    # 5190 registered to first, 5191 has a live listener, 5192 fails the bind probe
    assert "claimed 5193" in output
    assert f'project = "{second}"' in registry_path.read_text()


def test_scan_without_existing_registry_uses_current_directory(tmp_path: Path, capsys, monkeypatch) -> None:
    project = tmp_path / "demo"
    project.mkdir()
    (project / "package.json").write_text(json.dumps({"scripts": {"dev": "vite --port 5190"}}))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PORTMANAGER_HOME", str(tmp_path / "missing-config"))
    monkeypatch.setattr(registry_module, "load_listeners", lambda: {})

    result = main(["scan"])

    output = capsys.readouterr().out
    assert result == 0
    assert str(project) in output
    assert "unmanaged" in output


def test_doctor_json_returns_structured_error_codes(tmp_path: Path, capsys, monkeypatch) -> None:
    project = tmp_path / "demo"
    project.mkdir()
    registry_path = tmp_path / "ports.toml"
    (project / "package.json").write_text(json.dumps({"scripts": {"dev": "vite --port 5190"}}))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(registry_module, "load_listeners", lambda: {})

    assert main(["--registry", str(registry_path), "init"]) == 0
    capsys.readouterr()
    result = main(["--registry", str(registry_path), "doctor", "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert result == 1
    assert payload["ok"] is False
    assert payload["errors"][0]["code"] == "unmanaged_binding"


def test_completions_print_shell_scripts(capsys) -> None:
    assert main(["completions", "bash"]) == 0
    bash_output = capsys.readouterr().out
    assert "complete -F _portmanager portmanager" in bash_output
    assert "projects" in bash_output

    assert main(["completions", "zsh"]) == 0
    zsh_output = capsys.readouterr().out
    assert "#compdef portmanager" in zsh_output
    assert "projects:Manage standalone projects" in zsh_output


def test_projects_add_creates_and_updates_standalone_project(tmp_path: Path, capsys, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    standalone = tmp_path / "standalone"
    workspace.mkdir()
    standalone.mkdir()
    registry_path = tmp_path / "ports.toml"
    monkeypatch.setattr(registry_module, "load_listeners", lambda: {})

    assert main(["--registry", str(registry_path), "init", "--root", str(workspace)]) == 0
    capsys.readouterr()

    assert main(["--registry", str(registry_path), "projects", "add", str(standalone)]) == 0
    assert capsys.readouterr().out.strip() == str(standalone.resolve())
    registry = registry_module.load_registry(registry_path)
    assert [(project.path_obj, project.status) for project in registry.projects] == [(standalone.resolve(), "active")]

    assert main(["--registry", str(registry_path), "projects", "add", str(standalone), "--status", "external"]) == 0
    capsys.readouterr()
    registry = registry_module.load_registry(registry_path)
    assert [(project.path_obj, project.status) for project in registry.projects] == [(standalone.resolve(), "external")]

    assert main(["--registry", str(registry_path), "projects", "list"]) == 0
    assert capsys.readouterr().out.strip() == f"{standalone.resolve()} [external]"


def test_projects_add_dry_run_writes_nothing(tmp_path: Path, capsys, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    standalone = tmp_path / "standalone"
    workspace.mkdir()
    standalone.mkdir()
    registry_path = tmp_path / "ports.toml"
    monkeypatch.setattr(registry_module, "load_listeners", lambda: {})

    assert main(["--registry", str(registry_path), "init", "--root", str(workspace)]) == 0
    capsys.readouterr()
    before = registry_path.read_text()

    def fail_write(*args, **kwargs) -> None:
        raise AssertionError("dry-run must not write registry artifacts")

    monkeypatch.setattr(cli_module, "write_registry", fail_write)
    monkeypatch.setattr(cli_module, "write_generated_artifacts", fail_write)

    result = main(["--registry", str(registry_path), "projects", "add", str(standalone), "--dry-run"])

    assert result == 0
    assert capsys.readouterr().out.strip() == f"would add project {standalone.resolve()}"
    assert registry_path.read_text() == before


def test_adopt_dry_run_reports_existing_binding_without_mutation(tmp_path: Path, capsys, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    project = workspace / "demo"
    project.mkdir(parents=True)
    registry_path = tmp_path / "ports.toml"
    (project / "package.json").write_text(json.dumps({"scripts": {"dev": "vite --port 5190"}}))
    monkeypatch.setattr(registry_module, "load_listeners", lambda: {})

    assert main(["--registry", str(registry_path), "init", "--root", str(workspace)]) == 0
    result = main(["--registry", str(registry_path), "adopt", str(project), "--dry-run"])

    output = capsys.readouterr().out
    assert result == 0
    assert "would adopt 5190 web [active]" in output
    assert "[[services]]" not in registry_path.read_text()


def test_release_rename_and_move_project_update_registry(tmp_path: Path, capsys, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    project = workspace / "demo"
    moved_project = workspace / "demo-renamed"
    project.mkdir(parents=True)
    moved_project.mkdir()
    registry_path = tmp_path / "ports.toml"
    monkeypatch.setattr(registry_module, "load_listeners", lambda: {})

    assert main(["--registry", str(registry_path), "init", "--root", str(workspace)]) == 0
    assert main(["--registry", str(registry_path), "claim", str(project), "web", "--kind", "web", "--port", "5190", "--adopt-existing"]) == 0
    assert main(["--registry", str(registry_path), "rename-service", str(project), "web", "frontend"]) == 0
    assert main(["--registry", str(registry_path), "move-project", str(project), str(moved_project)]) == 0
    assert main(["--registry", str(registry_path), "release", str(moved_project), "frontend"]) == 0

    capsys.readouterr()
    text = registry_path.read_text()
    assert f'project = "{moved_project}"' in text
    assert 'service = "frontend"' in text
    assert 'status = "retired"' in text


def test_claim_requires_adopt_existing_for_explicit_port(tmp_path: Path, capsys, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    project = workspace / "demo"
    project.mkdir(parents=True)
    registry_path = tmp_path / "ports.toml"
    monkeypatch.setattr(registry_module, "load_listeners", lambda: {})

    assert main(["--registry", str(registry_path), "init", "--root", str(workspace)]) == 0
    before = registry_path.read_text()
    capsys.readouterr()

    result = main(["--registry", str(registry_path), "claim", str(project), "web", "--kind", "web", "--port", "5190"])

    captured = capsys.readouterr()
    assert result == 1
    assert "--port skips auto-assign conflict detection" in captured.err
    assert registry_path.read_text() == before


def test_claim_runs_doctor_unless_disabled(tmp_path: Path, capsys, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    project = workspace / "demo"
    project.mkdir(parents=True)
    registry_path = tmp_path / "ports.toml"
    (project / "package.json").write_text(json.dumps({"scripts": {"dev": "vite --port 5191"}}))
    monkeypatch.setattr(registry_module, "load_listeners", lambda: {})

    assert main(["--registry", str(registry_path), "init", "--root", str(workspace)]) == 0
    claim_args = [
        "--registry",
        str(registry_path),
        "claim",
        str(project),
        "web",
        "--kind",
        "web",
        "--port",
        "5190",
        "--adopt-existing",
    ]
    capsys.readouterr()

    assert main(claim_args) == 1
    assert "ERROR: unmanaged binding" in capsys.readouterr().out

    assert main([*claim_args, "--no-doctor"]) == 0
    assert "doctor:" not in capsys.readouterr().out


def test_sync_runs_doctor_unless_disabled(tmp_path: Path, capsys, monkeypatch) -> None:
    project = tmp_path / "demo"
    project.mkdir()
    registry_path = tmp_path / "ports.toml"
    (project / "package.json").write_text(json.dumps({"scripts": {"dev": "vite --port 5190"}}))
    monkeypatch.setattr(registry_module, "load_listeners", lambda: {})

    assert main(["--registry", str(registry_path), "init", "--root", str(tmp_path)]) == 0
    capsys.readouterr()

    sync_args = ["--registry", str(registry_path), "sync", str(project)]
    assert main(sync_args) == 1
    assert "ERROR: unmanaged binding" in capsys.readouterr().out

    assert main([*sync_args, "--no-doctor"]) == 0
    assert "doctor:" not in capsys.readouterr().out


def test_set_status_moves_a_service_between_lifecycle_states(tmp_path: Path, capsys, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    project = workspace / "demo"
    project.mkdir(parents=True)
    registry_path = tmp_path / "ports.toml"
    monkeypatch.setattr(registry_module, "load_listeners", lambda: {})

    assert main(["--registry", str(registry_path), "init", "--root", str(workspace)]) == 0
    assert main(["--registry", str(registry_path), "claim", str(project), "web", "--kind", "web"]) == 0
    capsys.readouterr()

    base = ["--registry", str(registry_path), "set-status", str(project), "web"]
    assert main([*base, "external", "--dry-run"]) == 0
    assert 'status = "active"' in registry_path.read_text()

    assert main([*base, "external", "--notes", "owned outside the workspace"]) == 0
    text = registry_path.read_text()
    assert 'status = "external"' in text
    assert "owned outside the workspace" in text

    assert main([*base, "active"]) == 0
    assert 'status = "active"' in registry_path.read_text()
    assert "owned outside the workspace" in registry_path.read_text()

    capsys.readouterr()
    assert main(["--registry", str(registry_path), "set-status", str(project), "nope", "active"]) == 1
    assert "no service named nope" in capsys.readouterr().err


def test_adopt_does_not_lose_bindings_that_share_a_service_name(tmp_path: Path, capsys, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    project = workspace / "demo"
    project.mkdir(parents=True)
    registry_path = tmp_path / "ports.toml"
    (project / "docker-compose.yml").write_text(
        "services:\n"
        "  db:\n"
        "    ports:\n"
        '      - "5432:5432"\n'
        "  redis:\n"
        "    ports:\n"
        '      - "6379:6379"\n'
    )
    (project / ".env").write_text("DB_PORT=5433\nREDIS_PORT=6380\n")
    monkeypatch.setattr(registry_module, "load_listeners", lambda: {})

    assert main(["--registry", str(registry_path), "init", "--root", str(workspace)]) == 0
    assert main(["--registry", str(registry_path), "adopt", str(project)]) == 0
    capsys.readouterr()

    text = registry_path.read_text()
    for port in ("5432", "5433", "6379", "6380"):
        assert f"port = {port}" in text, f"adopt dropped port {port}"
