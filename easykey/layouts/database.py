"""SQLite-backed layout store."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import List, Optional, Tuple


class LayoutDatabase:
    """Manages keyboard layout definitions and keycode tables."""

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            db_path = Path.home() / ".easykey" / "layouts.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self._ensure_schema()
        self._seed_keycodes()

    def _ensure_schema(self) -> None:
        schema_path = Path(__file__).with_name("schema.sql")
        with sqlite3.connect(self.db_path) as conn:
            if schema_path.exists():
                conn.executescript(schema_path.read_text())
            conn.commit()

    def _seed_keycodes(self) -> None:
        """Seed common VIA keycodes if table is empty."""
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute("SELECT COUNT(*) FROM keycodes")
            if cur.fetchone()[0] > 0:
                return
            defaults = [
                # Standard keys
                ("KC_A", 0x0004, "standard", "A", ""),
                ("KC_B", 0x0005, "standard", "B", ""),
                ("KC_C", 0x0006, "standard", "C", ""),
                ("KC_D", 0x0007, "standard", "D", ""),
                ("KC_E", 0x0008, "standard", "E", ""),
                ("KC_F", 0x0009, "standard", "F", ""),
                ("KC_G", 0x000A, "standard", "G", ""),
                ("KC_H", 0x000B, "standard", "H", ""),
                ("KC_I", 0x000C, "standard", "I", ""),
                ("KC_J", 0x000D, "standard", "J", ""),
                ("KC_K", 0x000E, "standard", "K", ""),
                ("KC_L", 0x000F, "standard", "L", ""),
                ("KC_M", 0x0010, "standard", "M", ""),
                ("KC_N", 0x0011, "standard", "N", ""),
                ("KC_O", 0x0012, "standard", "O", ""),
                ("KC_P", 0x0013, "standard", "P", ""),
                ("KC_Q", 0x0014, "standard", "Q", ""),
                ("KC_R", 0x0015, "standard", "R", ""),
                ("KC_S", 0x0016, "standard", "S", ""),
                ("KC_T", 0x0017, "standard", "T", ""),
                ("KC_U", 0x0018, "standard", "U", ""),
                ("KC_V", 0x0019, "standard", "V", ""),
                ("KC_W", 0x001A, "standard", "W", ""),
                ("KC_X", 0x001B, "standard", "X", ""),
                ("KC_Y", 0x001C, "standard", "Y", ""),
                ("KC_Z", 0x001D, "standard", "Z", ""),
                ("KC_1", 0x001E, "standard", "1", "!"),
                ("KC_2", 0x001F, "standard", "2", "@"),
                ("KC_3", 0x0020, "standard", "3", "#"),
                ("KC_4", 0x0021, "standard", "4", "$"),
                ("KC_5", 0x0022, "standard", "5", "%"),
                ("KC_6", 0x0023, "standard", "6", "^"),
                ("KC_7", 0x0024, "standard", "7", "&"),
                ("KC_8", 0x0025, "standard", "8", "*"),
                ("KC_9", 0x0026, "standard", "9", "("),
                ("KC_0", 0x0027, "standard", "0", ")"),
                ("KC_ENT", 0x0028, "standard", "Enter", ""),
                ("KC_ESC", 0x0029, "standard", "Esc", ""),
                ("KC_BSPC", 0x002A, "standard", "Backspace", ""),
                ("KC_TAB", 0x002B, "standard", "Tab", ""),
                ("KC_SPC", 0x002C, "standard", "Space", ""),
                ("KC_MINS", 0x002D, "standard", "-", "_"),
                ("KC_EQL", 0x002E, "standard", "=", "+"),
                ("KC_LBRC", 0x002F, "standard", "[", "{"),
                ("KC_RBRC", 0x0030, "standard", "]", "}"),
                ("KC_BSLS", 0x0031, "standard", "\\", "|"),
                ("KC_NUHS", 0x0032, "standard", "#", "~"),
                ("KC_SCLN", 0x0033, "standard", ";", ":"),
                ("KC_QUOT", 0x0034, "standard", "'", '"'),
                ("KC_GRV", 0x0035, "standard", "`", "~"),
                ("KC_COMM", 0x0036, "standard", ",", "<"),
                ("KC_DOT", 0x0037, "standard", ".", ">"),
                ("KC_SLSH", 0x0038, "standard", "/", "?"),
                ("KC_CAPS", 0x0039, "standard", "Caps Lock", ""),
                ("KC_F1", 0x003A, "standard", "F1", ""),
                ("KC_F2", 0x003B, "standard", "F2", ""),
                ("KC_F3", 0x003C, "standard", "F3", ""),
                ("KC_F4", 0x003D, "standard", "F4", ""),
                ("KC_F5", 0x003E, "standard", "F5", ""),
                ("KC_F6", 0x003F, "standard", "F6", ""),
                ("KC_F7", 0x0040, "standard", "F7", ""),
                ("KC_F8", 0x0041, "standard", "F8", ""),
                ("KC_F9", 0x0042, "standard", "F9", ""),
                ("KC_F10", 0x0043, "standard", "F10", ""),
                ("KC_F11", 0x0044, "standard", "F11", ""),
                ("KC_F12", 0x0045, "standard", "F12", ""),
                # Modifiers
                ("KC_LCTL", 0x00E0, "modifier", "Left Ctrl", ""),
                ("KC_LSFT", 0x00E1, "modifier", "Left Shift", ""),
                ("KC_LALT", 0x00E2, "modifier", "Left Alt", ""),
                ("KC_LGUI", 0x00E3, "modifier", "Left Cmd/Win", ""),
                ("KC_RCTL", 0x00E4, "modifier", "Right Ctrl", ""),
                ("KC_RSFT", 0x00E5, "modifier", "Right Shift", ""),
                ("KC_RALT", 0x00E6, "modifier", "Right Alt", ""),
                ("KC_RGUI", 0x00E7, "modifier", "Right Cmd/Win", ""),
                # Media
                ("KC_MPLY", 0x00CD, "media", "Play/Pause", ""),
                ("KC_MPRV", 0x00B6, "media", "Previous Track", ""),
                ("KC_MNXT", 0x00B5, "media", "Next Track", ""),
                ("KC_MUTE", 0x00E2, "media", "Mute", ""),
                ("KC_VOLD", 0x00EA, "media", "Volume Down", ""),
                ("KC_VOLU", 0x00E9, "media", "Volume Up", ""),
                # Layer actions (placeholder keycodes)
                ("MO(1)", 0x0100, "layer", "Momentary Layer 1", ""),
                ("MO(2)", 0x0101, "layer", "Momentary Layer 2", ""),
                ("MO(3)", 0x0102, "layer", "Momentary Layer 3", ""),
                ("TG(1)", 0x0103, "layer", "Toggle Layer 1", ""),
                ("TG(2)", 0x0104, "layer", "Toggle Layer 2", ""),
                ("TG(3)", 0x0105, "layer", "Toggle Layer 3", ""),
                # No-op
                ("KC_NO", 0x0000, "noop", "No-op", ""),
            ]
            conn.executemany(
                "INSERT INTO keycodes (name, code, category, label, description) VALUES (?,?,?,?,?)",
                defaults,
            )
            conn.commit()

    def add_keyboard(
        self,
        via_name: str,
        display_name: str,
        vendor_id: Optional[int],
        product_id: Optional[int],
        rows: int,
        cols: int,
        num_keys: int,
        kle_json: Optional[str] = None,
    ) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                """
                INSERT INTO keyboards (via_name, display_name, vendor_id, product_id, rows, cols, num_keys, kle_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(via_name) DO UPDATE SET
                    display_name=excluded.display_name,
                    vendor_id=excluded.vendor_id,
                    product_id=excluded.product_id,
                    rows=excluded.rows,
                    cols=excluded.cols,
                    num_keys=excluded.num_keys,
                    kle_json=excluded.kle_json
                RETURNING id
                """,
                (via_name, display_name, vendor_id, product_id, rows, cols, num_keys, kle_json),
            )
            row = cur.fetchone()
            conn.commit()
            return row[0]

    def get_keyboard_by_name(self, via_name: str) -> Optional[dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT * FROM keyboards WHERE via_name = ?", (via_name,)
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def add_key_positions(self, keyboard_id: int, positions: List[Tuple]) -> None:
        """positions: list of (matrix_row, matrix_col, x, y, width, height, legend)"""
        with sqlite3.connect(self.db_path) as conn:
            conn.executemany(
                """
                INSERT INTO key_positions (keyboard_id, matrix_row, matrix_col, x, y, width, height, legend)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [(keyboard_id, *p) for p in positions],
            )
            conn.commit()

    def get_key_positions(self, keyboard_id: int) -> List[dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT * FROM key_positions WHERE keyboard_id = ? ORDER BY id",
                (keyboard_id,),
            )
            return [dict(row) for row in cur.fetchall()]

    def search_keycodes(self, query: str, category: Optional[str] = None) -> List[dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            sql = "SELECT * FROM keycodes WHERE label LIKE ? OR name LIKE ?"
            params = [f"%{query}%", f"%{query}%"]
            if category:
                sql += " AND category = ?"
                params.append(category)
            sql += " ORDER BY CASE WHEN label LIKE ? THEN 0 ELSE 1 END, label"
            params.append(f"%{query}%")
            cur = conn.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]

    def get_keycode_by_name(self, name: str) -> Optional[dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute("SELECT * FROM keycodes WHERE name = ?", (name,))
            row = cur.fetchone()
            return dict(row) if row else None
