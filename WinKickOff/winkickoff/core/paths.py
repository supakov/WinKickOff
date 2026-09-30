"""Portable paths: everything is resolved from the folder that holds the executable.

Rules:
- never rely on the current working directory: for a shortcut launch it is unpredictable;
- never write outside the application folder (no per-user or per-machine profile folders, no system temp, no registry);
- data folders (rules, templates, resources, profiles) live in `data`, which is the repository
  checkout when running from sources and `_internal` inside a PyInstaller onedir build.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppPaths:
    root: Path
    data: Path
    docs_root: Path
    profiles: Path
    output: Path
    logs: Path

    @property
    def rules(self) -> Path:
        return self.data / "rules"

    @property
    def templates(self) -> Path:
        return self.data / "templates"

    @property
    def resources(self) -> Path:
        return self.data / "resources"

    @property
    def settings_file(self) -> Path:
        return self.root / "settings.json"

    @property
    def admx(self) -> Path:
        """Imported policy templates (core/admx.py), next to the settings; created on the first import."""
        return self.root / "admx"


def app_paths(*, create: bool = True) -> AppPaths:
    """Resolve the application folders.

    Frozen build:  root = folder of the exe, data = sys._MEIPASS (root/_internal), docs = data/docs.
    From sources:  root = WinKickOff/, data = root, docs = repository root (root's parent),
                   because docs/technical/reference and docs/user live one level above the package folder.
    """
    if getattr(sys, "frozen", False):
        root = Path(sys.executable).resolve().parent
        data = Path(getattr(sys, "_MEIPASS", root / "_internal"))
        docs_root = data
    else:
        root = Path(__file__).resolve().parents[2]
        data = root
        docs_root = root.parent
    paths = AppPaths(
        root=root,
        data=data,
        docs_root=docs_root,
        profiles=root / "profiles",
        output=root / "output",
        logs=root / "logs",
    )
    if create:
        for folder in (paths.profiles, paths.output, paths.logs):
            folder.mkdir(parents=True, exist_ok=True)
    return paths


def display_path(path: Path, root: Path) -> str:
    """Path relative to root when inside it (for settings and messages), else absolute."""
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path.resolve())
