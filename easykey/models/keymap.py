"""In-memory keymap model with undo/redo stack."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional


@dataclass
class KeyBinding:
    """Represents the binding assigned to a single key position."""

    keycode: int
    label: str = ""
    secondary_label: str = ""
    category: str = "standard"  # standard, media, layer, macro, mouse, noop
    is_staged: bool = False
    is_modified: bool = False

    def to_dict(self) -> dict:
        return {
            "keycode": self.keycode,
            "label": self.label,
            "secondary_label": self.secondary_label,
            "category": self.category,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "KeyBinding":
        return cls(
            keycode=d.get("keycode", 0),
            label=d.get("label", ""),
            secondary_label=d.get("secondary_label", ""),
            category=d.get("category", "standard"),
            is_modified=d.get("is_modified", False),
        )


@dataclass
class Layer:
    """Represents one keyboard layer."""

    index: int
    name: str
    bindings: List[KeyBinding] = field(default_factory=list)
    trigger_key: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "name": self.name,
            "bindings": [b.to_dict() for b in self.bindings],
            "trigger_key": self.trigger_key,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Layer":
        return cls(
            index=d["index"],
            name=d["name"],
            bindings=[KeyBinding.from_dict(b) for b in d.get("bindings", [])],
            trigger_key=d.get("trigger_key"),
        )


class ReorderLayerCommand:
    """Undoable command for layer reordering."""

    def __init__(self, old_index: int, new_index: int, layers_snapshot: List[Layer]):
        self.old_index = old_index
        self.new_index = new_index
        self.layers_snapshot = layers_snapshot

    def __repr__(self) -> str:
        return f"Reorder layer {self.old_index} -> {self.new_index}"


class RemapCommand:
    """Undoable command for a single key remap."""

    def __init__(
        self,
        layer_index: int,
        key_index: int,
        old_binding: KeyBinding,
        new_binding: KeyBinding,
    ):
        self.layer_index = layer_index
        self.key_index = key_index
        self.old_binding = old_binding
        self.new_binding = new_binding

    def __repr__(self) -> str:
        return (
            f"Remap {self.old_binding.label} -> {self.new_binding.label} "
            f"on layer {self.layer_index}"
        )


class UndoStack:
    """Command-pattern undo/redo stack."""

    def __init__(self, max_size: int = 200):
        self._undo: List[RemapCommand] = []
        self._redo: List[RemapCommand] = []
        self._max_size = max_size

    def push(self, cmd: RemapCommand) -> None:
        self._undo.append(cmd)
        if len(self._undo) > self._max_size:
            self._undo.pop(0)
        self._redo.clear()

    def can_undo(self) -> bool:
        return len(self._undo) > 0

    def can_redo(self) -> bool:
        return len(self._redo) > 0

    def undo(self) -> Optional[RemapCommand]:
        if not self._undo:
            return None
        cmd = self._undo.pop()
        self._redo.append(cmd)
        return cmd

    def redo(self) -> Optional[RemapCommand]:
        if not self._redo:
            return None
        cmd = self._redo.pop()
        self._undo.append(cmd)
        return cmd

    def peek_undo(self) -> Optional[RemapCommand]:
        return self._undo[-1] if self._undo else None

    def clear(self) -> None:
        self._undo.clear()
        self._redo.clear()


class Keymap:
    """In-memory model of the full keyboard keymap."""

    def __init__(self, keyboard_name: str, num_keys: int):
        self.keyboard_name = keyboard_name
        self.num_keys = num_keys
        self.layers: List[Layer] = []
        self.undo_stack = UndoStack()
        self._staged_count = 0
        self._change_callbacks: List[Callable[[], None]] = []

    def add_change_callback(self, cb: Callable[[], None]) -> None:
        self._change_callbacks.append(cb)

    def _notify(self) -> None:
        for cb in self._change_callbacks:
            cb()

    def add_layer(self, name: str) -> Layer:
        layer = Layer(index=len(self.layers), name=name)
        layer.bindings = [
            KeyBinding(keycode=0, label="", category="noop")
            for _ in range(self.num_keys)
        ]
        self.layers.append(layer)
        return layer

    def get_binding(self, layer_index: int, key_index: int) -> KeyBinding:
        return self.layers[layer_index].bindings[key_index]

    def set_binding(
        self, layer_index: int, key_index: int, binding: KeyBinding, stage: bool = True
    ) -> None:
        layer = self.layers[layer_index]
        old = layer.bindings[key_index]
        cmd = RemapCommand(layer_index, key_index, old, binding)
        self.undo_stack.push(cmd)
        binding.is_staged = stage
        if not stage:
            binding.is_modified = True
        layer.bindings[key_index] = binding
        if stage and not old.is_staged:
            self._staged_count += 1
        self._notify()

    def apply_staged(self) -> None:
        """Commit all staged bindings."""
        for layer in self.layers:
            for b in layer.bindings:
                if b.is_staged:
                    b.is_staged = False
                    b.is_modified = True
        self._staged_count = 0
        self._notify()

    def discard_staged(self) -> None:
        """Revert staged bindings using undo stack."""
        while self._staged_count > 0 and self.undo_stack.can_undo():
            cmd = self.undo_stack.undo()
            if cmd is None:
                break
            layer = self.layers[cmd.layer_index]
            layer.bindings[cmd.key_index] = cmd.old_binding
            self._staged_count -= 1
        self._staged_count = 0
        self._notify()

    def undo(self) -> Optional[RemapCommand]:
        cmd = self.undo_stack.undo()
        if cmd is None:
            return None
        if isinstance(cmd, ReorderLayerCommand):
            self.layers = cmd.layers_snapshot
            for i, layer in enumerate(self.layers):
                layer.index = i
            self._notify()
            return cmd
        layer = self.layers[cmd.layer_index]
        layer.bindings[cmd.key_index] = cmd.old_binding
        if cmd.new_binding.is_staged:
            self._staged_count -= 1
        self._notify()
        return cmd

    def redo(self) -> Optional[RemapCommand]:
        cmd = self.undo_stack.redo()
        if cmd is None:
            return None
        if isinstance(cmd, ReorderLayerCommand):
            # Re-apply the reorder
            idx = cmd.old_index
            new_idx = cmd.new_index
            self.layers[idx], self.layers[new_idx] = (
                self.layers[new_idx],
                self.layers[idx],
            )
            for i, layer in enumerate(self.layers):
                layer.index = i
            self._notify()
            return cmd
        layer = self.layers[cmd.layer_index]
        layer.bindings[cmd.key_index] = cmd.new_binding
        if cmd.new_binding.is_staged:
            self._staged_count += 1
        self._notify()
        return cmd

    def staged_count(self) -> int:
        return self._staged_count

    def to_dict(self) -> dict:
        return {
            "keyboard_name": self.keyboard_name,
            "num_keys": self.num_keys,
            "layers": [layer.to_dict() for layer in self.layers],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Keymap":
        km = cls(d["keyboard_name"], d["num_keys"])
        for layer_dict in d.get("layers", []):
            km.layers.append(Layer.from_dict(layer_dict))
        return km
