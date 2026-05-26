from __future__ import annotations

import os
import tempfile
from pathlib import Path

REGISTRY_FILE_NAME = "ports.toml"
LOCK_FILE_NAME = "ports.lock.json"
REPORT_FILE_NAME = "PORTS.md"


def user_config_dir() -> Path:
    override = os.environ.get("PORTMANAGER_HOME")
    if override:
        return Path(override).expanduser().resolve()
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config_home:
        return Path(xdg_config_home).expanduser().resolve() / "portmanager"
    return Path.home().expanduser().resolve() / ".config" / "portmanager"


def user_registry_path() -> Path:
    return user_config_dir() / REGISTRY_FILE_NAME


def find_nearest_registry(start: Path | None = None) -> Path | None:
    current = (start or Path.cwd()).expanduser().resolve()
    if current.is_file():
        current = current.parent
    for candidate_dir in [current, *current.parents]:
        candidate = candidate_dir / REGISTRY_FILE_NAME
        if candidate.exists():
            return candidate
    return None


def resolve_registry_path(value: str | Path | None = None, *, require_existing: bool = False) -> Path:
    if value:
        path = Path(value).expanduser().resolve()
    elif os.environ.get("PORTMANAGER_REGISTRY"):
        path = Path(os.environ["PORTMANAGER_REGISTRY"]).expanduser().resolve()
    else:
        path = find_nearest_registry() or user_registry_path()
    if require_existing and not path.exists():
        raise FileNotFoundError(f"registry not found: {path}")
    return path


def artifact_paths(registry_path: Path) -> tuple[Path, Path]:
    base = registry_path.expanduser().resolve().parent
    return base / LOCK_FILE_NAME, base / REPORT_FILE_NAME


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(text)
        temp_path = Path(handle.name)
    temp_path.replace(path)
