"""Layer tab bar with diff visualization."""

from __future__ import annotations

import copy
import tkinter as tk
from tkinter import simpledialog, ttk
from typing import Callable, Dict, List, Optional

from easykey.models.keymap import Keymap, Layer, ReorderLayerCommand


class LayerTabs(ttk.Frame):
    """ttk.Notebook-based layer selector with reorder, rename, and diff view."""

    def __init__(
        self,
        parent: tk.Widget,
        keymap: Keymap,
        on_layer_change: Callable[[int], None],
        on_diff_toggle: Optional[Callable[[bool], None]] = None,
        trigger_names: Optional[Dict[int, str]] = None,
    ) -> None:
        super().__init__(parent)
        self.keymap = keymap
        self.on_layer_change = on_layer_change
        self.on_diff_toggle = on_diff_toggle
        self.trigger_names = trigger_names or {}

        self._tab_frames: List[ttk.Frame] = []
        self.diff_view = tk.BooleanVar(value=True)

        self._build_ui()
        self.update_tabs()

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.notebook = ttk.Notebook(self)
        self.notebook.grid(row=0, column=0, sticky="nsew")

        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=0, column=1, sticky="ns", padx=4)

        self.up_btn = ttk.Button(
            btn_frame, text="▲", width=2, command=lambda: self._move_layer(-1)
        )
        self.up_btn.pack(pady=2)

        self.down_btn = ttk.Button(
            btn_frame, text="▼", width=2, command=lambda: self._move_layer(1)
        )
        self.down_btn.pack(pady=2)

        self.diff_chk = ttk.Checkbutton(
            btn_frame,
            text="Diff view",
            variable=self.diff_view,
            command=self._on_diff_clicked,
        )
        self.diff_chk.pack(pady=6)

        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        self.notebook.bind("<Double-Button-1>", self._on_double_click)

    def update_tabs(self, select_index: Optional[int] = None) -> None:
        """Rebuild notebook tabs from the current keymap layers."""
        for tab in list(self.notebook.tabs()):
            self.notebook.forget(tab)
        for frame in self._tab_frames:
            frame.destroy()
        self._tab_frames.clear()

        for i, layer in enumerate(self.keymap.layers):
            frame = ttk.Frame(self.notebook)
            self._tab_frames.append(frame)
            status = self._status_emoji(layer)
            trigger = self._trigger_label(layer)
            text = f"{layer.name}   {status}   [{trigger}]"
            self.notebook.add(frame, text=text)

        if self._tab_frames:
            idx = select_index if select_index is not None else 0
            idx = max(0, min(idx, len(self._tab_frames) - 1))
            self.notebook.select(self._tab_frames[idx])

        self._update_button_states()

    def current_layer_index(self) -> int:
        """Return the index of the currently selected tab."""
        try:
            return self.notebook.index(self.notebook.select())
        except tk.TclError:
            return 0

    def _status_emoji(self, layer: Layer) -> str:
        if any(b.is_staged for b in layer.bindings):
            return "🔵"
        if any(b.is_modified for b in layer.bindings):
            return "🟠"
        return "⚪"

    def _trigger_label(self, layer: Layer) -> str:
        if layer.trigger_key is None:
            return "?"
        return self.trigger_names.get(layer.trigger_key, f"0x{layer.trigger_key:04X}")

    def _on_tab_changed(self, event: tk.Event) -> None:
        idx = self.current_layer_index()
        self._update_button_states()
        self.on_layer_change(idx)

    def _on_double_click(self, event: tk.Event) -> None:
        try:
            idx = self.notebook.index(f"@{event.x},{event.y}")
        except tk.TclError:
            return
        self._rename_layer(idx)

    def _rename_layer(self, index: int) -> None:
        layer = self.keymap.layers[index]
        new_name = simpledialog.askstring(
            "Rename Layer", "Layer name:", initialvalue=layer.name
        )
        if new_name:
            layer.name = new_name
            self.update_tabs(select_index=index)

    def _move_layer(self, direction: int) -> None:
        idx = self.current_layer_index()
        if idx < 0:
            return
        new_idx = idx + direction
        if new_idx < 0 or new_idx >= len(self.keymap.layers):
            return
        # Snapshot layers for undo
        layers_snapshot = [copy.deepcopy(layer) for layer in self.keymap.layers]
        cmd = ReorderLayerCommand(idx, new_idx, layers_snapshot)
        self.keymap.undo_stack.push(cmd)
        self.keymap.layers[idx], self.keymap.layers[new_idx] = (
            self.keymap.layers[new_idx],
            self.keymap.layers[idx],
        )
        for i, layer in enumerate(self.keymap.layers):
            layer.index = i
        self.update_tabs(select_index=new_idx)
        self.on_layer_change(new_idx)

    def _update_button_states(self) -> None:
        idx = self.current_layer_index()
        self.up_btn.config(state="normal" if idx > 0 else "disabled")
        self.down_btn.config(
            state="normal" if idx < len(self.keymap.layers) - 1 else "disabled"
        )

    def _on_diff_clicked(self) -> None:
        if self.on_diff_toggle:
            self.on_diff_toggle(self.diff_view.get())
