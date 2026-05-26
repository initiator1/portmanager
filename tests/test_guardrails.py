from __future__ import annotations

from pathlib import Path

import portmanager.guardrails as guardrails_module
from portmanager.guardrails import build_antigravity_workflow, build_managed_block, install_guardrails, upsert_managed_block
from portmanager.models import ProjectEntry, Registry, RootEntry


def test_build_managed_block_mentions_scope() -> None:
    registry = Registry(
        roots=[RootEntry("/workspace/projects")],
        projects=[ProjectEntry("/workspace/external/photo-tool")],
    )

    block = build_managed_block(registry)

    assert "/workspace/projects" in block
    assert "/workspace/external/photo-tool" in block
    assert "5190-5299" in block


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
    gemini_path = tmp_path / ".gemini" / "GEMINI.md"
    antigravity_path = tmp_path / ".gemini" / "antigravity" / "global_workflows" / "portmanager_policy.md"
    monkeypatch.setattr(guardrails_module, "CODEX_HOME_GUARDRAIL_PATH", codex_path)
    monkeypatch.setattr(guardrails_module, "CLAUDE_HOME_GUARDRAIL_PATH", claude_path)
    monkeypatch.setattr(guardrails_module, "GEMINI_HOME_GUARDRAIL_PATH", gemini_path)
    monkeypatch.setattr(guardrails_module, "ANTIGRAVITY_GLOBAL_WORKFLOW_PATH", antigravity_path)

    registry = Registry(
        roots=[RootEntry("/workspace/projects")],
        projects=[ProjectEntry("/workspace/external/photo-tool")],
    )

    touched_first = install_guardrails(registry)
    touched_second = install_guardrails(registry)

    assert antigravity_path.resolve() in touched_first
    assert antigravity_path.resolve() in touched_second
    assert "portmanager claim" in antigravity_path.read_text()
    assert antigravity_path.read_text().count("# Portmanager Policy") == 1
    assert "<!-- PORTMANAGER:START -->" in gemini_path.read_text()
