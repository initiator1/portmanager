from __future__ import annotations

from pathlib import Path

CODEX_HOME_GUARDRAIL_PATH = Path.home() / ".codex" / "AGENTS.md"
CLAUDE_HOME_GUARDRAIL_PATH = Path.home() / ".claude" / "CLAUDE.md"
GEMINI_HOME_GUARDRAIL_PATH = Path.home() / ".gemini" / "GEMINI.md"
ANTIGRAVITY_GLOBAL_WORKFLOW_PATH = Path.home() / ".gemini" / "antigravity" / "global_workflows" / "portmanager_policy.md"

DEFAULT_BIND_HOST = "127.0.0.1"
MANAGED_RANGE_START = 5190
MANAGED_RANGE_END = 5299

IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    ".next",
    ".turbo",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "coverage",
    "target",
}

SCAN_FILE_NAMES = {
    "package.json",
    "vite.config.ts",
    "vite.config.js",
    "next.config.ts",
    "next.config.js",
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yaml",
    ".env",
    ".env.example",
    ".env.local",
    ".env.development",
    "pyproject.toml",
}

MANAGED_BLOCK_START = "<!-- PORTMANAGER:START -->"
MANAGED_BLOCK_END = "<!-- PORTMANAGER:END -->"
