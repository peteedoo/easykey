"""Unit tests for LayoutDatabase."""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from easykey.layouts.database import LayoutDatabase


def test_search_keycodes():
    with tempfile.TemporaryDirectory() as tmpdir:
        db = LayoutDatabase(Path(tmpdir) / "test.db")
        results = db.search_keycodes("A")
        names = [r["name"] for r in results]
        assert "KC_A" in names


def test_get_keycode_by_name():
    with tempfile.TemporaryDirectory() as tmpdir:
        db = LayoutDatabase(Path(tmpdir) / "test.db")
        row = db.get_keycode_by_name("KC_ESC")
        assert row is not None
        assert row["label"] == "Esc"


def test_add_keyboard():
    with tempfile.TemporaryDirectory() as tmpdir:
        db = LayoutDatabase(Path(tmpdir) / "test.db")
        kb_id = db.add_keyboard("test-kb", "Test Keyboard", 0x1234, 0x5678, 4, 12, 48)
        assert kb_id is not None
        row = db.get_keyboard_by_name("test-kb")
        assert row is not None
        assert row["display_name"] == "Test Keyboard"


if __name__ == "__main__":
    test_search_keycodes()
    test_get_keycode_by_name()
    test_add_keyboard()
    print("All database tests passed.")
