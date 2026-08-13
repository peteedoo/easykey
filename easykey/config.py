"""Application configuration and paths."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

APP_NAME = "EasyKey"
APP_VERSION = "1.0.0"


class Config:
    """Simple JSON-backed preferences store."""

    def __init__(self, config_dir: Optional[Path] = None):
        if config_dir is None:
            config_dir = Path.home() / ".easykey"
        self.config_dir = config_dir
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.prefs_path = self.config_dir / "prefs.json"
        self._data: Dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        if self.prefs_path.exists():
            try:
                with open(self.prefs_path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except Exception:
                self._data = {}

    def save(self) -> None:
        with open(self.prefs_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2)

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self.save()
