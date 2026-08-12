"""Unit tests for the keymap model."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from easykey.models.keymap import KeyBinding, Keymap, Layer


def test_create_keymap():
    km = Keymap("Test", 4)
    assert km.keyboard_name == "Test"
    assert km.num_keys == 4


def test_add_layer():
    km = Keymap("Test", 4)
    layer = km.add_layer("Base")
    assert layer.name == "Base"
    assert len(layer.bindings) == 4


def test_set_binding():
    km = Keymap("Test", 4)
    km.add_layer("Base")
    binding = KeyBinding(keycode=0x04, label="A")
    km.set_binding(0, 0, binding)
    assert km.get_binding(0, 0).label == "A"
    assert km.staged_count() == 1


def test_undo_redo():
    km = Keymap("Test", 4)
    km.add_layer("Base")
    b1 = KeyBinding(keycode=0x04, label="A")
    km.set_binding(0, 0, b1)
    assert km.staged_count() == 1

    km.undo()
    assert km.get_binding(0, 0).label == ""
    assert km.staged_count() == 0

    km.redo()
    assert km.get_binding(0, 0).label == "A"
    assert km.staged_count() == 1


def test_discard_staged():
    km = Keymap("Test", 4)
    km.add_layer("Base")
    km.set_binding(0, 0, KeyBinding(keycode=0x04, label="A"))
    km.set_binding(0, 1, KeyBinding(keycode=0x05, label="B"))
    assert km.staged_count() == 2

    km.discard_staged()
    assert km.staged_count() == 0
    assert km.get_binding(0, 0).label == ""
    assert km.get_binding(0, 1).label == ""


def test_serialize():
    km = Keymap("Test", 2)
    km.add_layer("Base")
    km.set_binding(0, 0, KeyBinding(keycode=0x04, label="A"))
    km.apply_staged()

    data = km.to_dict()
    km2 = Keymap.from_dict(data)
    assert km2.keyboard_name == "Test"
    assert km2.layers[0].bindings[0].label == "A"


if __name__ == "__main__":
    test_create_keymap()
    test_add_layer()
    test_set_binding()
    test_undo_redo()
    test_discard_staged()
    test_serialize()
    print("All keymap tests passed.")
