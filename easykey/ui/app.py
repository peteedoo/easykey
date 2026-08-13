"""Main application window for EasyKey."""

from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any, Dict, List, Optional, Tuple

from easykey.config import Config
from easykey.detection.hid_scanner import KeyboardInfo
from easykey.layouts.database import LayoutDatabase
from easykey.layouts.kle_parser import KLEParser
from easykey.models.keymap import KeyBinding, Keymap
from easykey.models.snapshot import SnapshotManager
from easykey.ui.layer_tabs import LayerTabs
from easykey.ui.wizard import FirstRunWizard

try:
    from easykey.ui.picker import PickerPanel
except Exception:  # pragma: no cover
    PickerPanel = None  # type: ignore

try:
    from easykey.detection import FirmwareRouter
except Exception:  # pragma: no cover
    FirmwareRouter = None  # type: ignore

try:
    from PIL import Image

    _HAS_PIL = True
except Exception:  # pragma: no cover
    _HAS_PIL = False

KEY_SIZE = 50
ROUND_RADIUS = 6

COLORS = {
    "default": "#ffffff",
    "default_outline": "#cccccc",
    "modified": "#ffbf00",
    "modified_outline": "#cc9900",
    "staged": "#20b2aa",
    "staged_outline": "#1a8f8a",
    "noop": "#a9a9a9",
    "noop_outline": "#808080",
    "focus": "#007aff",
}


class EasyKeyApp:
    """Top-level Tkinter application for the EasyKey configurator."""

    def __init__(self, root: Optional[tk.Tk] = None) -> None:
        """Initialise the application window, menus, and UI chrome."""
        self.root = root or tk.Tk()
        self.root.title("EasyKey")
        self.root.geometry("1200x800")
        self.root.minsize(800, 600)

        self.config = Config()
        self.snapshot_manager = SnapshotManager(Path.home() / ".easykey" / "snapshots")
        self.layout_db = LayoutDatabase()

        self.keymap: Optional[Keymap] = None
        self._keyboard_name = ""
        self._kle_data = ""
        self._keyboard_info: Optional[KeyboardInfo] = None
        self.zoom = 1.0
        self.high_contrast = False
        self.font_scale = 1.0
        self.test_mode = False

        # Canvas item storage
        self._key_rects: List[int] = []
        self._key_texts: List[int] = []
        self._key_shapes: List[Tuple[int, int, int]] = []
        self._key_focus_ring = 0
        self._focused_key_index = 0

        self._picker_window: Optional[tk.Toplevel] = None

        self._setup_styles()
        self._build_menu()
        self.setup_ui()
        self._bind_shortcuts()
        self._maybe_show_wizard()

    # ------------------------------------------------------------------ #
    #  Styles & chrome
    # ------------------------------------------------------------------ #

    def _setup_styles(self) -> None:
        """Configure ttk styles for a native but polished look."""
        style = ttk.Style(self.root)
        style.configure("Toolbar.TFrame", background="#f0f0f0")
        style.configure("Status.TLabel", background="#e0e0e0", padding=4)

    def _build_menu(self) -> None:
        """Create the menubar with all required menus."""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        # File
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Export Layout Image…", command=self._export_layout_image)
        file_menu.add_separator()
        file_menu.add_command(label="Import Snapshot…", command=self._import_snapshot)
        file_menu.add_command(label="Export Snapshot…", command=self._export_snapshot)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_close)
        menubar.add_cascade(label="File", menu=file_menu)

        # Edit
        self._edit_menu = tk.Menu(menubar, tearoff=0)
        self._edit_menu.add_command(label="Undo", command=self._do_undo)
        self._edit_menu.add_command(label="Redo", command=self._do_redo)
        menubar.add_cascade(label="Edit", menu=self._edit_menu)

        # View
        view_menu = tk.Menu(menubar, tearoff=0)
        zoom_menu = tk.Menu(view_menu, tearoff=0)
        for z in (0.75, 1.0, 1.25, 1.5):
            zoom_menu.add_command(
                label=f"{int(z * 100)}%",
                command=lambda z=z: self._set_zoom(z),
            )
        view_menu.add_cascade(label="Zoom", menu=zoom_menu)
        view_menu.add_separator()
        self._hc_var = tk.BooleanVar(value=False)
        view_menu.add_checkbutton(
            label="High Contrast Mode",
            variable=self._hc_var,
            command=self._toggle_high_contrast,
        )
        font_menu = tk.Menu(view_menu, tearoff=0)
        for label, scale in (("Small", 0.75), ("Default", 1.0), ("Large", 1.25)):
            font_menu.add_command(
                label=label,
                command=lambda s=scale: self._set_font_scale(s),
            )
        view_menu.add_cascade(label="Font Scale", menu=font_menu)
        menubar.add_cascade(label="View", menu=view_menu)

        # Help
        help_menu = tk.Menu(menubar, tearoff=0)
        self._test_var = tk.BooleanVar(value=False)
        help_menu.add_checkbutton(
            label="Test Mode",
            variable=self._test_var,
            command=self._toggle_test_mode,
        )
        menubar.add_cascade(label="Help", menu=help_menu)

    def setup_ui(self) -> None:
        """Build toolbar, layer tabs, canvas, and status bar."""
        # Toolbar
        self.toolbar = ttk.Frame(self.root, padding=4, style="Toolbar.TFrame")
        self.toolbar.pack(side=tk.TOP, fill=tk.X)

        self._staged_var = tk.StringVar(value="0 staged changes")
        ttk.Label(self.toolbar, textvariable=self._staged_var).pack(side=tk.LEFT, padx=4)

        self._undo_var = tk.StringVar(value="")
        ttk.Label(self.toolbar, textvariable=self._undo_var).pack(side=tk.LEFT, padx=4)

        ttk.Button(self.toolbar, text="Review", command=self._on_review).pack(side=tk.LEFT, padx=2)
        ttk.Button(self.toolbar, text="Apply", command=self.on_apply).pack(side=tk.LEFT, padx=2)
        ttk.Button(self.toolbar, text="Discard", command=self.on_discard).pack(side=tk.LEFT, padx=2)

        # Main area
        self.main_frame = ttk.Frame(self.root)
        self.main_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        dummy_keymap = Keymap("", 0)
        self.layer_tabs = LayerTabs(
            self.main_frame,
            keymap=dummy_keymap,
            on_layer_change=self._on_layer_changed,
            on_diff_toggle=self._on_diff_toggle,
        )
        self.layer_tabs.pack(side=tk.TOP, fill=tk.X)

        # Canvas with scrollbars
        self.canvas_frame = ttk.Frame(self.main_frame)
        self.canvas_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(
            self.canvas_frame,
            bg="#f5f5f5",
            highlightthickness=0,
            takefocus=1,
        )
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.h_scroll = ttk.Scrollbar(
            self.canvas_frame, orient=tk.HORIZONTAL, command=self.canvas.xview
        )
        self.h_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        self.v_scroll = ttk.Scrollbar(
            self.canvas_frame, orient=tk.VERTICAL, command=self.canvas.yview
        )
        self.v_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.canvas.configure(
            xscrollcommand=self.h_scroll.set,
            yscrollcommand=self.v_scroll.set,
        )

        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        self.status_bar = ttk.Label(
            self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W
        )
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        # Canvas keyboard nav
        self.canvas.bind("<Tab>", self._on_tab_next)
        self.canvas.bind("<Shift-Tab>", self._on_tab_prev)
        self.canvas.bind("<Return>", self._on_enter_key)
        self.canvas.bind("<Escape>", self._on_escape)

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------ #
    #  Keyboard loading & rendering
    # ------------------------------------------------------------------ #

    def load_keyboard(
        self, keyboard_name: str, kle_data: str, keyboard_info: Optional[KeyboardInfo] = None
    ) -> None:
        """Parse *kle_data* and render the keyboard on the canvas.

        A new :class:`Keymap` is created with a single **Base** layer seeded
        from the KLE legends.
        """
        if not kle_data:
            kle_data = self._blank_kle()
        self._keyboard_name = keyboard_name
        self._kle_data = kle_data
        self._keyboard_info = keyboard_info

        keys = KLEParser.parse(kle_data)
        positions = KLEParser.keys_to_positions(keys, scale=KEY_SIZE * self.zoom)
        num_keys = len(positions)

        self.keymap = Keymap(keyboard_name, num_keys)
        base = self.keymap.add_layer("Base")
        for i, (_, _, _, _, legend) in enumerate(positions):
            base.bindings[i] = KeyBinding(
                keycode=0, label=legend, category="standard"
            )

        self.keymap.add_change_callback(self._on_keymap_changed)
        self.layer_tabs.keymap = self.keymap
        self.layer_tabs.update_tabs()

        self._render_keys(positions)
        self._update_ui()

    def _blank_kle(self) -> str:
        """Return a minimal 4×12 KLE JSON string as a fallback."""
        row = [{"w": 1, "h": 1}] * 12
        return json.dumps([row for _ in range(4)])

    def _render_keys(
        self, positions: List[Tuple[float, float, float, float, str]]
    ) -> None:
        """Draw every key on the canvas and bind interactions."""
        self.canvas.delete("all")
        self._key_rects.clear()
        self._key_texts.clear()
        self._key_shapes.clear()

        offset_x = 20
        offset_y = 20
        radius = ROUND_RADIUS * self.zoom

        for i, (x, y, w, h, legend) in enumerate(positions):
            x1 = x + offset_x
            y1 = y + offset_y
            x2 = x1 + w - 2
            y2 = y1 + h - 2

            rect_id = self._draw_rounded_rect(
                x1,
                y1,
                x2,
                y2,
                radius,
                fill=COLORS["default"],
                outline=COLORS["default_outline"],
                tags=(f"key_{i}", "key_rect"),
            )
            text_id = self.canvas.create_text(
                (x1 + x2) / 2,
                (y1 + y2) / 2,
                text=legend,
                font=self._key_font(),
                tags=(f"key_{i}", "key_text"),
            )

            # High-contrast shapes (hidden initially)
            pad = 8 * self.zoom
            circle = self._draw_shape(
                x1, y1, x2, y2, "circle",
                fill="#000000", outline="#000000",
                tags=(f"key_{i}", "shape_default", "key_shape"),
            )
            triangle = self._draw_shape(
                x1, y1, x2, y2, "triangle",
                fill="#000000", outline="#000000",
                tags=(f"key_{i}", "shape_modified", "key_shape"),
            )
            square = self._draw_shape(
                x1, y1, x2, y2, "square",
                fill="#000000", outline="#000000",
                tags=(f"key_{i}", "shape_staged", "key_shape"),
            )
            for sid in (circle, triangle, square):
                self.canvas.itemconfig(sid, state="hidden")

            # Bind click
            for item_id in (rect_id, text_id, circle, triangle, square):
                self.canvas.tag_bind(
                    item_id, "<Button-1>", lambda e, idx=i: self.on_key_click(idx)
                )

            self._key_rects.append(rect_id)
            self._key_texts.append(text_id)
            self._key_shapes.append((circle, triangle, square))

        # Focus ring (topmost)
        self._key_focus_ring = self.canvas.create_rectangle(
            0, 0, 0, 0,
            outline=COLORS["focus"], width=2, state="hidden",
        )
        self.canvas.tag_raise(self._key_focus_ring)

        # Scroll region
        bbox = self.canvas.bbox("all")
        if bbox:
            self.canvas.config(
                scrollregion=(bbox[0] - 10, bbox[1] - 10, bbox[2] + 10, bbox[3] + 10)
            )

        self._focused_key_index = 0
        if self._key_rects:
            self._update_focus_ring()

    def refresh_canvas(self) -> None:
        """Redraw all keys using current binding state, diff view, and high-contrast mode."""
        if self.keymap is None or not self._key_rects:
            return

        layer_index = self.layer_tabs.current_layer_index()
        if layer_index >= len(self.keymap.layers):
            layer_index = 0
        layer = self.keymap.layers[layer_index]
        base_layer = self.keymap.layers[0] if self.keymap.layers else layer

        diff_view = self.layer_tabs.diff_view.get()

        for i, binding in enumerate(layer.bindings):
            rect_id = self._key_rects[i]
            text_id = self._key_texts[i]
            shapes = self._key_shapes[i]

            # Opacity for inherited keys on non-base layers
            opacity = 1.0
            if layer_index != 0 and diff_view:
                if self._binding_eq(binding, base_layer.bindings[i]):
                    opacity = 0.4

            # Update legend text
            self.canvas.itemconfig(text_id, text=binding.label or "")

            if self.high_contrast:
                self.canvas.itemconfig(
                    rect_id,
                    fill=COLORS["default"],
                    outline=COLORS["default_outline"],
                )
                for sid in shapes:
                    self.canvas.itemconfig(sid, state="hidden")
                if binding.category != "noop":
                    if binding.is_staged:
                        shape_idx = 2  # square
                    elif binding.is_modified:
                        shape_idx = 1  # triangle
                    else:
                        shape_idx = 0  # circle
                    self.canvas.itemconfig(shapes[shape_idx], state="normal")
            else:
                # Color coding
                if binding.category == "noop":
                    fill = COLORS["noop"]
                    outline = COLORS["noop_outline"]
                elif binding.is_staged:
                    fill = COLORS["staged"]
                    outline = COLORS["staged_outline"]
                elif binding.is_modified:
                    fill = COLORS["modified"]
                    outline = COLORS["modified_outline"]
                else:
                    fill = COLORS["default"]
                    outline = COLORS["default_outline"]

                if opacity < 1.0:
                    fill = self._blend_color(fill, self.canvas["bg"], opacity)
                    self.canvas.itemconfig(text_id, fill="#888888")
                else:
                    self.canvas.itemconfig(text_id, fill="#000000")

                self.canvas.itemconfig(rect_id, fill=fill, outline=outline)

        self._update_focus_ring()
        self._update_ui()

    # ------------------------------------------------------------------ #
    #  Helpers
    # ------------------------------------------------------------------ #

    def _draw_rounded_rect(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        radius: float,
        **kwargs: Any,
    ) -> int:
        points = self._rounded_rect_points(x1, y1, x2, y2, radius)
        return self.canvas.create_polygon(points, smooth=True, **kwargs)

    def _rounded_rect_points(
        self, x1: float, y1: float, x2: float, y2: float, r: float
    ) -> List[float]:
        r = min(r, (x2 - x1) / 2, (y2 - y1) / 2)
        pts: List[float] = []
        pts.extend([x1 + r, y1, x2 - r, y1])
        pts.extend([x2, y1, x2, y1 + r])
        pts.extend([x2, y2 - r, x2, y2])
        pts.extend([x2 - r, y2, x1 + r, y2])
        pts.extend([x1, y2, x1, y2 - r])
        pts.extend([x1, y1 + r, x1, y1])
        return pts

    def _draw_shape(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        shape: str,
        **kwargs: Any,
    ) -> int:
        pad = 8 * self.zoom
        cx = (x1 + x2) / 2
        if shape == "circle":
            return self.canvas.create_oval(
                x1 + pad, y1 + pad, x2 - pad, y2 - pad, **kwargs
            )
        if shape == "square":
            return self.canvas.create_rectangle(
                x1 + pad, y1 + pad, x2 - pad, y2 - pad, **kwargs
            )
        if shape == "triangle":
            return self.canvas.create_polygon(
                cx, y1 + pad,
                x2 - pad, y2 - pad,
                x1 + pad, y2 - pad,
                **kwargs,
            )
        return self.canvas.create_rectangle(x1, y1, x2, y2, **kwargs)

    def _key_font(self) -> Tuple[str, int]:
        size = int(10 * self.zoom * self.font_scale)
        return ("TkDefaultFont", max(size, 6))

    @staticmethod
    def _blend_color(c1: str, c2: str, alpha: float) -> str:
        def _hex_to_rgb(h: str) -> Tuple[int, int, int]:
            h = h.lstrip("#")
            if len(h) == 3:
                h = "".join([ch * 2 for ch in h])
            return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))

        def _rgb_to_hex(r: int, g: int, b: int) -> str:
            return f"#{r:02x}{g:02x}{b:02x}"

        r1, g1, b1 = _hex_to_rgb(c1)
        r2, g2, b2 = _hex_to_rgb(c2)
        a = max(0.0, min(1.0, alpha))
        return _rgb_to_hex(
            int(r1 * a + r2 * (1 - a)),
            int(g1 * a + g2 * (1 - a)),
            int(b1 * a + b2 * (1 - a)),
        )

    @staticmethod
    def _binding_eq(a: KeyBinding, b: KeyBinding) -> bool:
        return (
            a.keycode == b.keycode
            and a.label == b.label
            and a.category == b.category
        )

    # ------------------------------------------------------------------ #
    #  UI update callbacks
    # ------------------------------------------------------------------ #

    def _on_keymap_changed(self) -> None:
        self.refresh_canvas()

    def _on_layer_changed(self, layer_index: int) -> None:
        self.refresh_canvas()

    def _on_diff_toggle(self, active: bool) -> None:
        self.refresh_canvas()

    def _update_ui(self) -> None:
        if self.keymap is None:
            self._staged_var.set("0 staged changes")
            self._undo_var.set("")
            self.status_var.set("Ready")
            self._edit_menu.entryconfig(0, state="disabled")
            self._edit_menu.entryconfig(1, state="disabled")
            return

        staged = self.keymap.staged_count()
        self._staged_var.set(
            f"{staged} staged change{'s' if staged != 1 else ''}"
        )

        peek = self.keymap.undo_stack.peek_undo()
        self._undo_var.set(f"Undo: {peek}" if peek else "")

        kb = self._keyboard_name or "No keyboard"
        self.status_var.set(
            f"{kb} | Zoom {int(self.zoom * 100)}% | "
            f"Layer {self.layer_tabs.current_layer_index()}"
        )

        self._edit_menu.entryconfig(
            0, state="normal" if self.keymap.undo_stack.can_undo() else "disabled"
        )
        self._edit_menu.entryconfig(
            1, state="normal" if self.keymap.undo_stack.can_redo() else "disabled"
        )

    # ------------------------------------------------------------------ #
    #  Interactions
    # ------------------------------------------------------------------ #

    def on_key_click(self, key_index: int) -> None:
        """Open the picker panel (or a fallback dialog) for the clicked key."""
        if self.keymap is None:
            return
        layer_index = self.layer_tabs.current_layer_index()
        binding = self.keymap.get_binding(layer_index, key_index)

        if PickerPanel is not None:
            self._open_picker(key_index, layer_index, binding)
        else:
            new_label = simpledialog.askstring(
                "Remap Key",
                f"New label for key {key_index} (layer {layer_index}):",
                initialvalue=binding.label,
            )
            if new_label is not None:
                new_binding = KeyBinding(
                    keycode=binding.keycode or 0,
                    label=new_label,
                    category="standard" if new_label else "noop",
                )
                self.keymap.set_binding(layer_index, key_index, new_binding, stage=True)

    def _open_picker(
        self, key_index: int, layer_index: int, binding: KeyBinding
    ) -> None:
        if self._picker_window is not None and self._picker_window.winfo_exists():
            self._picker_window.destroy()

        def on_save(new_binding: KeyBinding) -> None:
            self.keymap.set_binding(layer_index, key_index, new_binding, stage=True)
            self._picker_window.destroy()
            self._picker_window = None

        def on_close() -> None:
            if self._picker_window is not None:
                self._picker_window.destroy()
                self._picker_window = None

        def on_apply_binding(new_binding: KeyBinding) -> None:
            self.keymap.set_binding(layer_index, key_index, new_binding, stage=True)
            on_close()

        self._picker_window = PickerPanel(
            parent=self.root,
            keymap=self.keymap,
            layer_index=layer_index,
            key_index=key_index,
            on_close=on_close,
            on_apply_binding=on_apply_binding,
        )

    def on_apply(self) -> None:
        """Check for conflicts, write to firmware (if available), and commit."""
        if self.keymap is None:
            return

        conflicts = self._check_conflicts()
        if conflicts:
            detail = "\n".join(conflicts)
            if not messagebox.askyesno(
                "Conflicts Detected",
                f"The following conflicts were found:\n\n{detail}\n\nApply anyway?",
            ):
                return

        if FirmwareRouter is not None and self._keyboard_info is not None:
            try:
                router = FirmwareRouter(self._keyboard_info)
                router.write_full_keymap(self.keymap)
                router.close()
            except Exception as exc:
                messagebox.showerror("Firmware Error", f"Failed to write firmware:\n{exc}")
                return
        else:
            print("[FirmwareRouter] Keymap write placeholder (no keyboard connected)")

        self.keymap.apply_staged()
        self.refresh_canvas()

    def on_discard(self) -> None:
        """Discard all staged changes after user confirmation."""
        if self.keymap is None:
            return
        if messagebox.askyesno(
            "Discard Changes", "Are you sure you want to discard all staged changes?"
        ):
            self.keymap.discard_staged()
            self.refresh_canvas()

    def _do_undo(self) -> None:
        if self.keymap and self.keymap.undo_stack.can_undo():
            self.keymap.undo()
            self.refresh_canvas()

    def _do_redo(self) -> None:
        if self.keymap and self.keymap.undo_stack.can_redo():
            self.keymap.redo()
            self.refresh_canvas()

    # ------------------------------------------------------------------ #
    #  Conflict checker
    # ------------------------------------------------------------------ #

    def _check_conflicts(self) -> List[str]:
        conflicts: List[str] = []
        if self.keymap is None:
            return conflicts
        for layer in self.keymap.layers:
            seen: Dict[int, int] = {}
            for i, b in enumerate(layer.bindings):
                if b.is_staged or b.is_modified:
                    if b.keycode != 0 and b.keycode in seen:
                        conflicts.append(
                            f"Layer '{layer.name}': duplicate keycode 0x{b.keycode:04X} "
                            f"on keys {seen[b.keycode]} and {i}"
                        )
                    seen[b.keycode] = i
        return conflicts

    # ------------------------------------------------------------------ #
    #  Menu actions
    # ------------------------------------------------------------------ #

    def _export_layout_image(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[
                ("PNG", "*.png"),
                ("PostScript", "*.ps"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return
        self.canvas.update()
        if path.lower().endswith(".ps"):
            self.canvas.postscript(file=path, colormode="color")
            return

        ps = Path(path).with_suffix(".ps")
        self.canvas.postscript(file=ps, colormode="color")
        if _HAS_PIL:
            try:
                with Image.open(ps) as img:
                    img.save(path)
                ps.unlink()
            except Exception as exc:
                messagebox.showerror("Export Error", str(exc))
        else:
            messagebox.showinfo(
                "Saved PostScript",
                f"PIL is not available. Layout saved as PostScript:\n{ps}",
            )

    def _import_snapshot(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if not path:
            return
        snap = self.snapshot_manager.import_file(Path(path))
        if snap:
            messagebox.showinfo(
                "Snapshot Imported", f"Imported snapshot from {snap.timestamp}"
            )
        else:
            messagebox.showerror("Error", "Failed to import snapshot.")

    def _export_snapshot(self) -> None:
        if self.keymap is None:
            messagebox.showwarning("No Keymap", "Load a keyboard first.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".json", filetypes=[("JSON", "*.json")]
        )
        if not path:
            return
        snap = self.snapshot_manager.save(
            self.keymap.keyboard_name,
            "",
            self.keymap,
        )
        if self.snapshot_manager.export(snap.timestamp, Path(path)):
            messagebox.showinfo("Snapshot Exported", f"Exported to {path}")
        else:
            messagebox.showerror("Error", "Failed to export snapshot.")

    def _on_review(self) -> None:
        if self.keymap is None:
            return
        top = tk.Toplevel(self.root)
        top.title("Review Staged Changes")
        top.geometry("400x300")
        top.transient(self.root)

        listbox = tk.Listbox(top)
        listbox.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        for layer in self.keymap.layers:
            for ki, b in enumerate(layer.bindings):
                if b.is_staged:
                    listbox.insert(tk.END, f"{layer.name} key {ki}: -> {b.label}")

        ttk.Button(top, text="Close", command=top.destroy).pack(pady=4)

    # ------------------------------------------------------------------ #
    #  View settings
    # ------------------------------------------------------------------ #

    def _set_zoom(self, zoom: float) -> None:
        self.zoom = zoom
        if self._kle_data:
            self.load_keyboard(self._keyboard_name, self._kle_data)

    def _toggle_high_contrast(self) -> None:
        self.high_contrast = self._hc_var.get()
        self.refresh_canvas()

    def _set_font_scale(self, scale: float) -> None:
        self.font_scale = scale
        self.canvas.itemconfig("key_text", font=self._key_font())

    def _toggle_test_mode(self) -> None:
        self.test_mode = self._test_var.get()
        self.status_var.set(f"Test mode {'ON' if self.test_mode else 'OFF'}")
        if self.test_mode:
            if not hasattr(self, '_test_overlay') or self._test_overlay is None:
                from easykey.ui.test_mode import TestModeOverlay
                self._test_overlay = TestModeOverlay(
                    parent=self.root,
                    keymap=self.keymap,
                    on_exit=self._exit_test_mode,
                )
        else:
            self._exit_test_mode()

    def _exit_test_mode(self) -> None:
        if hasattr(self, '_test_overlay') and self._test_overlay is not None:
            self._test_overlay._do_exit()
            self._test_overlay = None
        self.test_mode = False
        self._test_var.set(False)
        self.status_var.set("Test mode OFF")

    # ------------------------------------------------------------------ #
    #  Keyboard navigation
    # ------------------------------------------------------------------ #

    def _bind_shortcuts(self) -> None:
        self.root.bind("<Command-z>", lambda e: self._do_undo())
        self.root.bind("<Control-z>", lambda e: self._do_undo())
        self.root.bind("<Command-Shift-Z>", lambda e: self._do_redo())
        self.root.bind("<Control-y>", lambda e: self._do_redo())
        self.root.bind("<Command-y>", lambda e: self._do_redo())

    def _on_tab_next(self, event: tk.Event) -> str:
        if not self._key_rects:
            return "break"
        self._focused_key_index = (self._focused_key_index + 1) % len(self._key_rects)
        self._update_focus_ring()
        return "break"

    def _on_tab_prev(self, event: tk.Event) -> str:
        if not self._key_rects:
            return "break"
        self._focused_key_index = (self._focused_key_index - 1) % len(self._key_rects)
        self._update_focus_ring()
        return "break"

    def _on_enter_key(self, event: tk.Event) -> str:
        if self._key_rects:
            self.on_key_click(self._focused_key_index)
        return "break"

    def _on_escape(self, event: tk.Event) -> str:
        if self._picker_window is not None and self._picker_window.winfo_exists():
            self._picker_window.destroy()
            self._picker_window = None
        return "break"

    def _update_focus_ring(self) -> None:
        if not self._key_rects:
            return
        i = self._focused_key_index
        bbox = self.canvas.bbox(self._key_rects[i])
        if bbox:
            pad = 3
            self.canvas.coords(
                self._key_focus_ring,
                bbox[0] - pad,
                bbox[1] - pad,
                bbox[2] + pad,
                bbox[3] + pad,
            )
            self.canvas.itemconfig(self._key_focus_ring, state="normal")
            self.canvas.tag_raise(self._key_focus_ring)

    # ------------------------------------------------------------------ #
    #  Wizard & lifecycle
    # ------------------------------------------------------------------ #

    def _maybe_show_wizard(self) -> None:
        if self.config.get("wizard_completed"):
            return
        wizard = FirstRunWizard(self.root, self.config)
        self.root.wait_window(wizard)
        if wizard.selected_keyboard:
            kle = wizard.selected_keyboard.get("kle_data", "")
            self.load_keyboard(
                wizard.selected_keyboard["name"],
                kle,
                wizard.selected_keyboard.get("keyboard_info"),
            )
        elif self.keymap is None:
            self._create_blank_keyboard()

    def _create_blank_keyboard(self) -> None:
        self.load_keyboard("Blank", self._blank_kle())

    def _on_close(self) -> None:
        if self.keymap and self.keymap.staged_count() > 0:
            if not messagebox.askyesno(
                "Unsaved Changes", "You have staged changes. Discard them?"
            ):
                return
        self.root.destroy()

    def run(self) -> None:
        """Start the Tkinter main loop."""
        self.root.mainloop()
