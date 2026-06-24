from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from app_meta import APP_ID

DEFAULT_START_URL = "https://pintia.cn/problem-sets/all"


def project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def resource_root() -> Path:
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base)
    return project_root()


def app_data_root() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path.home() / ".local" / "share"
    candidates = [
        base / APP_ID,
        project_root() / ".appdata" / APP_ID,
    ]
    for path in candidates:
        try:
            path.mkdir(parents=True, exist_ok=True)
            return path
        except OSError:
            continue
    raise OSError("Could not create an application data directory.")


def ensure_subdir(primary_base: Path, fallback_base: Path, name: str) -> Path:
    candidates = [
        primary_base / name,
        fallback_base / name,
    ]
    for path in candidates:
        try:
            path.mkdir(parents=True, exist_ok=True)
            return path
        except OSError:
            continue
    raise OSError(f"Could not create required application subdirectory: {name}")


@dataclass(slots=True)
class AppConfig:
    start_url: str
    output_dir: Path
    session_profile_dir: Path
    temp_dir: Path
    embed_images: bool = True

    @classmethod
    def load_default(cls) -> "AppConfig":
        base = app_data_root()
        fallback_base = project_root() / ".appdata" / APP_ID
        fallback_base.mkdir(parents=True, exist_ok=True)
        output_dir = ensure_subdir(base, fallback_base, "exports")
        profile_dir = ensure_subdir(base, fallback_base, "pta-profile")
        temp_dir = ensure_subdir(base, fallback_base, "tmp")
        return cls(
            start_url=DEFAULT_START_URL,
            output_dir=output_dir,
            session_profile_dir=profile_dir,
            temp_dir=temp_dir,
            embed_images=True,
        )
