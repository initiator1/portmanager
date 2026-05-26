from __future__ import annotations

import json
from pathlib import Path

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


def test_claim_dry_run_does_not_create_registry(tmp_path: Path, capsys, monkeypatch) -> None:
    registry_path = tmp_path / "ports.toml"
    project = tmp_path / "demo"
    project.mkdir()
    monkeypatch.setattr(registry_module, "load_listeners", lambda: {})

    result = main(["--registry", str(registry_path), "claim", str(project), "web", "--kind", "web", "--dry-run"])

    output = capsys.readouterr().out
    assert result == 0
    assert "would claim" in output
    assert not registry_path.exists()


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
    assert main(["--registry", str(registry_path), "claim", str(project), "web", "--kind", "web", "--port", "5190"]) == 0
    assert main(["--registry", str(registry_path), "rename-service", str(project), "web", "frontend"]) == 0
    assert main(["--registry", str(registry_path), "move-project", str(project), str(moved_project)]) == 0
    assert main(["--registry", str(registry_path), "release", str(moved_project), "frontend"]) == 0

    capsys.readouterr()
    text = registry_path.read_text()
    assert f'project = "{moved_project}"' in text
    assert 'service = "frontend"' in text
    assert 'status = "retired"' in text
