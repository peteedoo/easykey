"""Click-to-remap picker panel."""

from __future__ import annotations

import re
import tkinter as tk
from tkinter import ttk
from typing import Callable, Dict, List, Optional

from easykey.config import Config
from easykey.layouts.database import LayoutDatabase
from easykey.models.keymap import KeyBinding, Keymap


class PickerPanel(ttk.Frame):
    """Slide-in picker panel for assigning key bindings.

    Designed to occupy a fixed 300 px width on the right side of the main
    window.  The parent application is responsible for packing or gridding
    this frame into the desired location.

    Example::

        picker = PickerPanel(
            parent=root,
            keymap=my_keymap,
            layer_index=0,
            key_index=5,
            on_close=lambda: picker.destroy(),
            on_apply_binding=lambda b: keymap.set_binding(0, 5, b),
        )
        picker.pack(side=tk.RIGHT, fill=tk.Y)
    """

    # Names of keycodes shown in the "Standard key" quick-pick grid.
    _COMMON_NAMES: tuple[str, ...] = (
        "KC_A",
        "KC_B",
        "KC_C",
        "KC_D",
        "KC_E",
        "KC_F",
        "KC_G",
        "KC_H",
        "KC_I",
        "KC_J",
        "KC_K",
        "KC_L",
        "KC_M",
        "KC_N",
        "KC_O",
        "KC_P",
        "KC_Q",
        "KC_R",
        "KC_S",
        "KC_T",
        "KC_U",
        "KC_V",
        "KC_W",
        "KC_X",
        "KC_Y",
        "KC_Z",
        "KC_1",
        "KC_2",
        "KC_3",
        "KC_4",
        "KC_5",
        "KC_6",
        "KC_7",
        "KC_8",
        "KC_9",
        "KC_0",
        "KC_ENT",
        "KC_ESC",
        "KC_BSPC",
        "KC_TAB",
        "KC_SPC",
        "KC_MINS",
        "KC_EQL",
        "KC_LBRC",
        "KC_RBRC",
        "KC_BSLS",
        "KC_SCLN",
        "KC_QUOT",
        "KC_GRV",
        "KC_COMM",
        "KC_DOT",
        "KC_SLSH",
        "KC_F1",
        "KC_F2",
        "KC_F3",
        "KC_F4",
        "KC_F5",
        "KC_F6",
        "KC_F7",
        "KC_F8",
        "KC_F9",
        "KC_F10",
        "KC_F11",
        "KC_F12",
        "KC_LCTL",
        "KC_LSFT",
        "KC_LALT",
        "KC_LGUI",
        "KC_RCTL",
        "KC_RSFT",
        "KC_RALT",
        "KC_RGUI",
    )

    # Media keys shown as quick buttons.
    _MEDIA_NAMES: tuple[str, ...] = (
        "KC_MPLY",
        "KC_MUTE",
        "KC_VOLD",
        "KC_VOLU",
    )

    # Modifier buttons and the search text they append.
    _MODIFIERS: tuple[tuple[str, str], ...] = (
        ("Ctrl+", "Ctrl"),
        ("Shift+", "Shift"),
        ("Alt+", "Alt"),
    )

    _MRU_MAX: int = 20
    _SEARCH_DEBOUNCE_MS: int = 150

    def __init__(
        self,
        parent: tk.Widget,
        keymap: Keymap,
        layer_index: int,
        key_index: int,
        on_close: Callable[[], None],
        on_apply_binding: Callable[[KeyBinding], None],
    ) -> None:
        """Create the picker panel.

        Args:
            parent: Tkinter parent widget.
            keymap: The active keymap model.
            layer_index: Index of the layer being edited.
            key_index: Index of the key position being remapped.
            on_close: Called when the panel should close (Escape or cancel).
            on_apply_binding: Called with the chosen :class:`KeyBinding`.
        """
        super().__init__(parent, width=300)
        self.pack_propagate(False)  # Keep width fixed at 300 px

        self.keymap = keymap
        self.layer_index = layer_index
        self.key_index = key_index
        self.on_close = on_close
        self.on_apply_binding = on_apply_binding

        self._db = LayoutDatabase()
        self._config = Config()

        self._search_var = tk.StringVar()
        self._advanced_visible = False
        self._search_after_id: Optional[str] = None
        self._esc_bind_id: Optional[str] = None

        self._build_ui()
        self._bind_events()
        self._load_current_binding()
        self._refresh_common_grid()

    # ------------------------------------------------------------------ #
    # UI construction
    # ------------------------------------------------------------------ #

    def _build_ui(self) -> None:
        """Assemble all widgets."""
        # ----- Header ---------------------------------------------------
        header = ttk.Frame(self)
        header.pack(fill=tk.X, padx=8, pady=(8, 4))

        self._current_label = ttk.Label(header, text="", font=("", 10, "bold"))
        self._current_label.pack(anchor=tk.W)

        ttk.Button(
            header, text="Reset to default", command=self._on_reset
        ).pack(anchor=tk.W, pady=(4, 0))

        ttk.Separator(self, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=8, pady=4)

        # ----- Search ---------------------------------------------------
        search_frame = ttk.Frame(self)
        search_frame.pack(fill=tk.X, padx=8, pady=4)
        ttk.Label(search_frame, text="Search:").pack(side=tk.LEFT)
        self._search_entry = ttk.Entry(search_frame, textvariable=self._search_var)
        self._search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))

        # ----- Scrollable content ---------------------------------------
        canvas = tk.Canvas(self, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=canvas.yview)
        self._content = ttk.Frame(canvas)

        self._content.bind(
            "<Configure>",
            lambda _event: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=self._content, anchor=tk.NW, width=280)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # -- Most Common -------------------------------------------------
        self._common_frame = ttk.LabelFrame(self._content, text="Most Common")
        self._common_frame.pack(fill=tk.X, padx=4, pady=4)

        # Standard key grid
        std_frame = ttk.LabelFrame(self._common_frame, text="Standard key")
        std_frame.pack(fill=tk.X, padx=4, pady=4)
        self._grid_frame = ttk.Frame(std_frame)
        self._grid_frame.pack(fill=tk.X, padx=4, pady=4)

        # Modifier combo
        mod_frame = ttk.LabelFrame(self._common_frame, text="Modifier combo")
        mod_frame.pack(fill=tk.X, padx=4, pady=4)
        for label, search_text in self._MODIFIERS:
            ttk.Button(
                mod_frame,
                text=label,
                command=lambda st=search_text: self._append_search(st),
            ).pack(side=tk.LEFT, padx=2, pady=2)

        # Media / system
        media_frame = ttk.LabelFrame(self._common_frame, text="Media / system key")
        media_frame.pack(fill=tk.X, padx=4, pady=4)
        for name in self._MEDIA_NAMES:
            record = self._db.get_keycode_by_name(name)
            if record:
                ttk.Button(
                    media_frame,
                    text=record["label"],
                    command=lambda r=record: self._on_select(r),
                ).pack(side=tk.LEFT, padx=2, pady=2)

        # No-op
        noop_frame = ttk.Frame(self._common_frame)
        noop_frame.pack(fill=tk.X, padx=4, pady=4)
        ttk.Button(
            noop_frame,
            text="No-op",
            command=lambda: self._apply_by_name("KC_NO"),
        ).pack(anchor=tk.W)

        # -- Advanced ----------------------------------------------------
        self._adv_btn = ttk.Button(
            self._content,
            text="▶ Advanced",
            command=self._toggle_advanced,
        )
        self._adv_btn.pack(fill=tk.X, padx=4, pady=4)

        self._advanced_frame = ttk.Frame(self._content)
        # Not packed initially — collapsed

        # Macro placeholder
        macro_lf = ttk.LabelFrame(self._advanced_frame, text="Macro")
        macro_lf.pack(fill=tk.X, padx=4, pady=4)
        ttk.Button(
            macro_lf,
            text="Record macro",
            command=lambda: print("Macro recording not yet implemented"),
        ).pack(anchor=tk.W, padx=4, pady=4)

        # Layer action
        layer_lf = ttk.LabelFrame(self._advanced_frame, text="Layer action")
        layer_lf.pack(fill=tk.X, padx=4, pady=4)
        for record in self._db.search_keycodes("", category="layer"):
            friendly = self._friendly_layer_label(record["name"], record["label"])
            btn_frame = ttk.Frame(layer_lf)
            btn_frame.pack(fill=tk.X, padx=2, pady=2)
            ttk.Button(
                btn_frame,
                text=friendly,
                command=lambda r=record: self._on_select(r),
            ).pack(fill=tk.X)
            ttk.Label(btn_frame, text=record["name"], font=("", 7)).pack(anchor=tk.W)

        # Mouse emulation placeholder
        mouse_lf = ttk.LabelFrame(self._advanced_frame, text="Mouse emulation")
        mouse_lf.pack(fill=tk.X, padx=4, pady=4)
        ttk.Button(
            mouse_lf,
            text="Mouse buttons (coming soon)",
            state=tk.DISABLED,
        ).pack(anchor=tk.W, padx=4, pady=4)

        # Text snippet placeholder
        text_lf = ttk.LabelFrame(self._advanced_frame, text="Text snippet")
        text_lf.pack(fill=tk.X, padx=4, pady=4)
        ttk.Button(
            text_lf,
            text="Insert snippet (coming soon)",
            state=tk.DISABLED,
        ).pack(anchor=tk.W, padx=4, pady=4)

    def _bind_events(self) -> None:
        """Bind keyboard shortcuts and search tracing."""
        self._search_trace_id = self._search_var.trace_add(
            "write", lambda *_args: self._on_search_changed()
        )

        root = self.winfo_toplevel()
        self._esc_bind_id = root.bind("<Escape>", self._on_escape, add=True)

    def _load_current_binding(self) -> None:
        """Display the current binding at the top of the panel."""
        binding = self.keymap.get_binding(self.layer_index, self.key_index)
        text = binding.label or binding.secondary_label or "Unassigned"
        self._current_label.configure(text=f"Current: {text}")

    # ------------------------------------------------------------------ #
    # Event handlers
    # ------------------------------------------------------------------ #

    def _on_search_changed(self) -> None:
        """Debounce search input to keep the UI responsive."""
        if self._search_after_id is not None:
            self.after_cancel(self._search_after_id)
        self._search_after_id = self.after(
            self._SEARCH_DEBOUNCE_MS, self._refresh_common_grid
        )

    def _on_escape(self, _event: tk.Event) -> None:  # type: ignore[type-arg]
        """Close the panel without applying changes."""
        self.on_close()

    # ------------------------------------------------------------------ #
    # Logic
    # ------------------------------------------------------------------ #

    def _refresh_common_grid(self) -> None:
        """Repopulate the standard-key grid based on search text and MRU."""
        for widget in self._grid_frame.winfo_children():
            widget.destroy()

        query = self._search_var.get().strip()
        if query:
            records = [
                r
                for r in self._db.search_keycodes(query)
                if r["category"] in ("standard", "modifier")
            ]
        else:
            records: List[Dict[str, object]] = []
            for name in self._COMMON_NAMES:
                rec = self._db.get_keycode_by_name(name)
                if rec:
                    records.append(rec)
            # MRU sort — most recent first
            mru: List[str] = self._config.get("mru_keys", [])
            mru_order = {name: idx for idx, name in enumerate(reversed(mru))}
            records.sort(key=lambda r: (mru_order.get(r["name"], -1), r["label"]))
            records.reverse()

        cols = 6
        for idx, rec in enumerate(records[:60]):  # Cap at 60 buttons
            tk.Button(
                self._grid_frame,
                text=rec["label"],
                width=4,
                height=1,
                font=("", 8),
                command=lambda r=rec: self._on_select(r),
            ).grid(
                row=idx // cols, column=idx % cols, padx=1, pady=1, sticky=tk.NSEW
            )

    def _on_select(self, record: Dict[str, object]) -> None:
        """Create a :class:`KeyBinding` from a DB record and apply it."""
        binding = KeyBinding(
            keycode=record["code"],
            label=record["label"],
            secondary_label=record.get("description", ""),
            category=record["category"],
        )
        self._push_mru(record["name"])
        self.on_apply_binding(binding)
        self.on_close()

    def _apply_by_name(self, name: str) -> None:
        """Look up a keycode by name and apply it."""
        record = self._db.get_keycode_by_name(name)
        if record:
            self._on_select(record)
        else:
            # Fallback for KC_NO if not present in the database.
            self.on_apply_binding(
                KeyBinding(keycode=0, label="No-op", category="noop")
            )
            self.on_close()

    def _on_reset(self) -> None:
        """Reset the key to its firmware default (KC_NO for v1)."""
        self.on_apply_binding(KeyBinding(keycode=0, label="No-op", category="noop"))
        self.on_close()

    def _append_search(self, text: str) -> None:
        """Append *text* to the search field and trigger a refresh."""
        current = self._search_var.get()
        if current and not current.endswith(" "):
            current += " "
        self._search_var.set(current + text)
        self._search_entry.icursor(tk.END)
        self._search_entry.focus()

    def _toggle_advanced(self) -> None:
        """Show or hide the advanced section."""
        self._advanced_visible = not self._advanced_visible
        if self._advanced_visible:
            self._advanced_frame.pack(fill=tk.X, padx=4, pady=4, before=self._adv_btn)
            self._adv_btn.configure(text="▼ Advanced")
        else:
            self._advanced_frame.pack_forget()
            self._adv_btn.configure(text="▶ Advanced")

    @staticmethod
    def _friendly_layer_label(name: str, db_label: str) -> str:
        """Return a user-friendly label for a layer action keycode.

        Converts ``MO(N)`` → "Hold for Layer N" and ``TG(N)`` →
        "Toggle Layer N".  Falls back to the database label for any
        other format.
        """
        mo_match = re.match(r"MO\((\d+)\)", name)
        if mo_match:
            return f"Hold for Layer {mo_match.group(1)}"
        tg_match = re.match(r"TG\((\d+)\)", name)
        if tg_match:
            return f"Toggle Layer {tg_match.group(1)}"
        return db_label

    def _push_mru(self, name: str) -> None:
        """Add *name* to the front of the most-recently-used list."""
        mru: List[str] = self._config.get("mru_keys", [])
        if name in mru:
            mru.remove(name)
        mru.insert(0, name)
        if len(mru) > self._MRU_MAX:
            mru = mru[: self._MRU_MAX]
        self._config.set("mru_keys", mru)

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    def destroy(self) -> None:
        """Clean up traces and bindings before destroying the widget."""
        if hasattr(self, "_search_trace_id"):
            try:
                self._search_var.trace_remove("write", self._search_trace_id)
            except tk.TclError:
                pass

        if self._esc_bind_id is not None:
            try:
                root = self.winfo_toplevel()
                root.unbind("<Escape>", self._esc_bind_id)
            except tk.TclError:
                pass
            self._esc_bind_id = None

        if self._search_after_id is not None:
            try:
                self.after_cancel(self._search_after_id)
            except tk.TclError:
                pass
            self._search_after_id = None

        super().destroy()
