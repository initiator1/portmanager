from __future__ import annotations

from pathlib import Path

import portmanager.guardrails as guardrails_module
import yaml
from portmanager.constants import CLAUDE_RULE_PATH_GLOBS
from portmanager.guardrails import (
    build_antigravity_workflow,
    build_managed_block,
    install_guardrails,
    legacy_block_removals,
    planned_guardrail_targets,
    remove_managed_block,
    upsert_managed_block,
)
from portmanager.models import ProjectEntry, Registry, RootEntry
from portmanager.registry import configured_project_paths


def test_build_managed_block_mentions_scope() -> None:
    registry = Registry(
        roots=[RootEntry("/workspace/projects")],
        projects=[ProjectEntry("/workspace/external/photo-tool")],
    )

    block = build_managed_block(registry)

    assert "/workspace/projects" in block
    assert "/workspace/external/photo-tool" in block
    assert "5190-5299" in block


def test_build_managed_block_excludes_retired_projects_from_scope() -> None:
    registry = Registry(
        roots=[RootEntry("/workspace/projects")],
        projects=[
            ProjectEntry("/workspace/active", status="active"),
            ProjectEntry("/workspace/retired", status="retired"),
        ],
    )

    block = build_managed_block(registry)
    scope_line = next(line for line in block.splitlines() if line.startswith("- Managed workspace scope:"))

    assert "`/workspace/active`" in scope_line
    assert "`/workspace/retired`" not in scope_line


def test_external_projects_are_reservation_only(tmp_path: Path, monkeypatch) -> None:
    """External projects hold ports but are never scanned or given instruction files."""
    external = tmp_path / "outside-workspace"
    external.mkdir()
    monkeypatch.setattr(guardrails_module, "CODEX_HOME_GUARDRAIL_PATH", tmp_path / ".codex" / "AGENTS.md")
    monkeypatch.setattr(guardrails_module, "CLAUDE_HOME_GUARDRAIL_PATH", tmp_path / ".claude" / "CLAUDE.md")
    monkeypatch.setattr(guardrails_module, "CLAUDE_HOME_RULE_PATH", tmp_path / ".claude" / "rules" / "pm.md")
    monkeypatch.setattr(guardrails_module, "GEMINI_HOME_GUARDRAIL_PATH", tmp_path / ".gemini" / "GEMINI.md")
    monkeypatch.setattr(guardrails_module, "ANTIGRAVITY_GLOBAL_WORKFLOW_PATH", tmp_path / ".gemini" / "flow.md")

    registry = Registry(roots=[], projects=[ProjectEntry(str(external), status="external")])

    block = build_managed_block(registry)
    scope_line = next(line for line in block.splitlines() if line.startswith("- Managed workspace scope:"))
    assert str(external) not in scope_line
    assert external.resolve() not in configured_project_paths(registry)
    assert not any(external in path.parents for path in planned_guardrail_targets(registry))

    install_guardrails(registry)
    assert not (external / "CLAUDE.md").exists()
    assert not (external / "AGENTS.md").exists()
    assert not (external / "GEMINI.md").exists()


def test_build_antigravity_workflow_mentions_scope_and_commands() -> None:
    registry = Registry(
        roots=[RootEntry("/workspace/projects")],
        projects=[ProjectEntry("/workspace/external/photo-tool")],
    )

    workflow = build_antigravity_workflow(registry)

    assert "/workspace/projects" in workflow
    assert "/workspace/external/photo-tool" in workflow
    assert "5190-5299" in workflow
    assert "portmanager claim" in workflow
    assert "portmanager sync" in workflow
    assert "portmanager doctor" in workflow


def test_upsert_managed_block_replaces_existing_block(tmp_path: Path) -> None:
    target = tmp_path / "AGENTS.md"
    target.write_text(
        "# AGENTS.md\n\n"
        "<!-- PORTMANAGER:START -->\nold block\n<!-- PORTMANAGER:END -->\n\n"
        "keep me\n"
    )

    upsert_managed_block(target, "AGENTS.md", "<!-- PORTMANAGER:START -->\nnew block\n<!-- PORTMANAGER:END -->")

    text = target.read_text()
    assert "new block" in text
    assert "old block" not in text
    assert "keep me" in text


def test_install_guardrails_writes_antigravity_workflow_and_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    codex_path = tmp_path / ".codex" / "AGENTS.md"
    claude_path = tmp_path / ".claude" / "CLAUDE.md"
    claude_rule_path = tmp_path / ".claude" / "rules" / "portmanager-ports.md"
    gemini_path = tmp_path / ".gemini" / "GEMINI.md"
    antigravity_path = tmp_path / ".gemini" / "antigravity" / "global_workflows" / "portmanager_policy.md"
    monkeypatch.setattr(guardrails_module, "CODEX_HOME_GUARDRAIL_PATH", codex_path)
    monkeypatch.setattr(guardrails_module, "CLAUDE_HOME_GUARDRAIL_PATH", claude_path)
    monkeypatch.setattr(guardrails_module, "CLAUDE_HOME_RULE_PATH", claude_rule_path)
    monkeypatch.setattr(guardrails_module, "GEMINI_HOME_GUARDRAIL_PATH", gemini_path)
    monkeypatch.setattr(guardrails_module, "ANTIGRAVITY_GLOBAL_WORKFLOW_PATH", antigravity_path)

    registry = Registry(
        roots=[RootEntry("/workspace/projects")],
        projects=[ProjectEntry("/workspace/external/photo-tool")],
    )
    claude_path.parent.mkdir(parents=True)
    claude_path.write_text(
        "# Claude instructions\n\n"
        "keep before\n\n"
        "<!-- PORTMANAGER:START -->\nold block\n<!-- PORTMANAGER:END -->\n\n"
        "keep after\n"
    )

    touched_first = install_guardrails(registry)
    touched_second = install_guardrails(registry)
    planned = planned_guardrail_targets(registry)

    assert antigravity_path.resolve() in touched_first
    assert antigravity_path.resolve() in touched_second
    assert claude_path.resolve() in touched_first
    assert claude_path.resolve() not in touched_second
    assert claude_rule_path.resolve() in touched_first
    assert claude_rule_path.resolve() in touched_second
    assert claude_rule_path.resolve() in planned
    assert claude_path.resolve() not in planned
    assert "portmanager claim" in antigravity_path.read_text()
    assert antigravity_path.read_text().count("# Portmanager Policy") == 1
    assert "<!-- PORTMANAGER:START -->" in gemini_path.read_text()
    assert claude_path.read_text() == "# Claude instructions\n\nkeep before\n\nkeep after\n"
    assert "<!-- PORTMANAGER:START -->" not in claude_path.read_text()

    rule_text = claude_rule_path.read_text()
    frontmatter = yaml.safe_load(rule_text.split("---", 2)[1])
    assert frontmatter == {"paths": list(CLAUDE_RULE_PATH_GLOBS)}
    for expected in [
        "5190-5299",
        "PM_PORT_",
        "PM_URL_",
        "ports.env",
        "--port",
        "portmanager claim",
        "portmanager sync",
        "portmanager doctor",
    ]:
        assert expected in rule_text


def test_legacy_block_removals_reports_only_files_still_carrying_a_block(tmp_path: Path, monkeypatch) -> None:
    claude_path = tmp_path / ".claude" / "CLAUDE.md"
    monkeypatch.setattr(guardrails_module, "CLAUDE_HOME_GUARDRAIL_PATH", claude_path)

    assert legacy_block_removals() == []

    claude_path.parent.mkdir(parents=True)
    claude_path.write_text("# Claude instructions\n\nkeep me\n")
    assert legacy_block_removals() == []

    claude_path.write_text(
        "# Claude instructions\n\n<!-- PORTMANAGER:START -->\nold block\n<!-- PORTMANAGER:END -->\n"
    )
    assert legacy_block_removals() == [claude_path.resolve()]

    remove_managed_block(claude_path)
    assert legacy_block_removals() == []
