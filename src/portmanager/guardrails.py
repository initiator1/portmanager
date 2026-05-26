from __future__ import annotations

from pathlib import Path

from .constants import (
    ANTIGRAVITY_GLOBAL_WORKFLOW_PATH,
    CLAUDE_HOME_GUARDRAIL_PATH,
    CODEX_HOME_GUARDRAIL_PATH,
    GEMINI_HOME_GUARDRAIL_PATH,
    MANAGED_BLOCK_END,
    MANAGED_BLOCK_START,
)
from .config import write_text_atomic
from .models import Registry


def _policy_lines(registry: Registry) -> list[str]:
    root_lines = [f"`{root.path}`" for root in registry.roots]
    project_lines = [f"`{project.path}`" for project in registry.projects]
    scope = ", ".join(root_lines + project_lines)
    return [
        f"- Managed workspace scope: {scope}",
        f"- Managed development port range: `{registry.managed_range_start}-{registry.managed_range_end}`",
        "- Never introduce or change a host-bound local port without first claiming it through `portmanager claim`.",
        "- Prefer `.portmanager/ports.env` plus `PM_PORT_*` and `PM_URL_*` over hardcoded localhost ports.",
        "- Before completing a port-related change, run `portmanager sync <project>` and `portmanager doctor <project>`.",
        "- If you find an unmanaged hardcoded port, replace it with env-backed consumption instead of choosing another default.",
    ]


def build_managed_block(registry: Registry) -> str:
    return "\n".join([MANAGED_BLOCK_START, "## Portmanager Policy", "", *_policy_lines(registry), MANAGED_BLOCK_END])


def build_antigravity_workflow(registry: Registry) -> str:
    return (
        "\n".join(
            [
                "# Portmanager Policy",
                "",
                "Apply this workflow whenever you are editing a project inside the managed local workspaces.",
                "",
                *_policy_lines(registry),
                "",
                "Recommended sequence for any new local service port:",
                "",
                "```bash",
                "uv run portmanager claim /absolute/project/path service --kind web",
                "uv run portmanager sync /absolute/project/path",
                "uv run portmanager doctor /absolute/project/path",
                "```",
            ]
        )
        + "\n"
    )


def upsert_managed_block(path: Path, title: str, body: str) -> None:
    if path.exists():
        text = path.read_text(errors="ignore")
    else:
        text = f"# {title}\n\n"
    if MANAGED_BLOCK_START in text and MANAGED_BLOCK_END in text:
        start = text.index(MANAGED_BLOCK_START)
        end = text.index(MANAGED_BLOCK_END) + len(MANAGED_BLOCK_END)
        updated = text[:start].rstrip() + "\n\n" + body + "\n"
        trailing = text[end:].lstrip()
        if trailing:
            updated += "\n" + trailing
        write_text_atomic(path, updated)
        return
    content = text.rstrip() + "\n\n" + body + "\n"
    write_text_atomic(path, content)


def write_owned_markdown(path: Path, body: str) -> None:
    write_text_atomic(path, body)


def planned_guardrail_targets(registry: Registry) -> list[Path]:
    targets = [
        (CODEX_HOME_GUARDRAIL_PATH, "AGENTS.md"),
        (CLAUDE_HOME_GUARDRAIL_PATH, "CLAUDE.md"),
        (GEMINI_HOME_GUARDRAIL_PATH, "GEMINI.md"),
    ]
    for root in registry.roots:
        root_path = root.path_obj
        if not root_path.exists():
            continue
        targets.extend(
            [
                (root_path / "AGENTS.md", "AGENTS.md"),
                (root_path / "CLAUDE.md", "CLAUDE.md"),
                (root_path / "GEMINI.md", "GEMINI.md"),
            ]
        )
    for project in registry.projects:
        if project.status not in {"active", "external"} or not project.path_obj.exists():
            continue
        targets.extend(
            [
                (project.path_obj / "AGENTS.md", "AGENTS.md"),
                (project.path_obj / "CLAUDE.md", "CLAUDE.md"),
                (project.path_obj / "GEMINI.md", "GEMINI.md"),
            ]
        )
    seen: set[Path] = set()
    planned: list[Path] = []
    for path, _title in targets:
        resolved = path.expanduser().resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        planned.append(resolved)
    planned.append(ANTIGRAVITY_GLOBAL_WORKFLOW_PATH.expanduser().resolve())
    return planned


def install_guardrails(registry: Registry) -> list[Path]:
    touched: list[Path] = []
    block = build_managed_block(registry)
    antigravity_workflow = build_antigravity_workflow(registry)
    targets = [
        (CODEX_HOME_GUARDRAIL_PATH, "AGENTS.md"),
        (CLAUDE_HOME_GUARDRAIL_PATH, "CLAUDE.md"),
        (GEMINI_HOME_GUARDRAIL_PATH, "GEMINI.md"),
    ]
    for root in registry.roots:
        root_path = root.path_obj
        if not root_path.exists():
            continue
        targets.extend(
            [
                (root_path / "AGENTS.md", "AGENTS.md"),
                (root_path / "CLAUDE.md", "CLAUDE.md"),
                (root_path / "GEMINI.md", "GEMINI.md"),
            ]
        )
    for project in registry.projects:
        if project.status not in {"active", "external"} or not project.path_obj.exists():
            continue
        targets.extend(
            [
                (project.path_obj / "AGENTS.md", "AGENTS.md"),
                (project.path_obj / "CLAUDE.md", "CLAUDE.md"),
                (project.path_obj / "GEMINI.md", "GEMINI.md"),
            ]
        )
    seen: set[Path] = set()
    for path, title in targets:
        resolved = path.expanduser().resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        upsert_managed_block(resolved, title, block)
        touched.append(resolved)
    antigravity_path = ANTIGRAVITY_GLOBAL_WORKFLOW_PATH.expanduser().resolve()
    write_owned_markdown(antigravity_path, antigravity_workflow)
    touched.append(antigravity_path)
    return touched
