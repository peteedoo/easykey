"""Backup/restore serialization and snapshot management."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from .keymap import Keymap


class Snapshot:
    """Represents a single keymap backup."""

    def __init__(
        self,
        timestamp: str,
        keyboard_name: str,
        firmware_version: str,
        keymap: Keymap,
        macros: Optional[dict] = None,
        diff_summary: str = "",
    ):
        self.timestamp = timestamp
        self.keyboard_name = keyboard_name
        self.firmware_version = firmware_version
        self.keymap = keymap
        self.macros = macros or {}
        self.diff_summary = diff_summary

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "keyboard_name": self.keyboard_name,
            "firmware_version": self.firmware_version,
            "keymap": self.keymap.to_dict(),
            "macros": self.macros,
            "diff_summary": self.diff_summary,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Snapshot":
        return cls(
            timestamp=d["timestamp"],
            keyboard_name=d["keyboard_name"],
            firmware_version=d.get("firmware_version", ""),
            keymap=Keymap.from_dict(d["keymap"]),
            macros=d.get("macros", {}),
            diff_summary=d.get("diff_summary", ""),
        )


class SnapshotManager:
    """Manages automatic and manual snapshots."""

    def __init__(self, backups_dir: Path, max_snapshots: int = 20):
        self.backups_dir = Path(backups_dir)
        self.backups_dir.mkdir(parents=True, exist_ok=True)
        self.max_snapshots = max_snapshots

    def _snapshot_path(self, timestamp: str) -> Path:
        return self.backups_dir / f"{timestamp}.json"

    def save(
        self,
        keyboard_name: str,
        firmware_version: str,
        keymap: Keymap,
        macros: Optional[dict] = None,
        diff_summary: str = "",
    ) -> Snapshot:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        snap = Snapshot(timestamp, keyboard_name, firmware_version, keymap, macros, diff_summary)
        path = self._snapshot_path(timestamp)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(snap.to_dict(), f, indent=2)
        self._prune()
        return snap

    def _prune(self) -> None:
        files = sorted(self.backups_dir.glob("*.json"), key=lambda p: p.stat().st_mtime)
        while len(files) > self.max_snapshots:
            files.pop(0).unlink()

    def list_snapshots(self) -> List[Snapshot]:
        snaps = []
        for path in sorted(self.backups_dir.glob("*.json"), reverse=True):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    snaps.append(Snapshot.from_dict(json.load(f)))
            except Exception:
                continue
        return snaps

    def restore(self, timestamp: str) -> Optional[Snapshot]:
        path = self._snapshot_path(timestamp)
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            return Snapshot.from_dict(json.load(f))

    def export(self, timestamp: str, destination: Path) -> bool:
        src = self._snapshot_path(timestamp)
        if not src.exists():
            return False
        shutil.copy2(src, destination)
        return True

    def import_file(self, path: Path) -> Optional[Snapshot]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            snap = Snapshot.from_dict(data)
            dest = self._snapshot_path(snap.timestamp)
            with open(dest, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            return snap
        except Exception:
            return None
