"""Live keystroke listener and visualiser (Test Mode)."""

from __future__ import annotations

import platform
import sys
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, Dict, List, Optional, Set

from easykey.layouts.database import LayoutDatabase
from easykey.models.keymap import Keymap

try:
    from pynput import keyboard as pynput_keyboard

    HAS_PYNPUT = True
except Exception:  # pragma: no cover
    HAS_PYNPUT = False


class TestModeOverlay(tk.Toplevel):
    """Fullscreen test overlay that visualises live keystrokes.

    The overlay renders the current keyboard layout and highlights keys as
    they are pressed.  If the received key differs from the programmed
    binding the key flashes red for 500 ms.

    Usage::

        overlay = TestModeOverlay(
            parent=root,
            keymap=my_keymap,
            on_exit=lambda: overlay.destroy(),
        )
    """

    # Mapping from common pynput / tk keysyms to key labels used in EasyKey.
    _KEY_NAME_MAP: Dict[str, str] = {
        "space": "Space",
        "Return": "Enter",
        "Enter": "Enter",
        "BackSpace": "Backspace",
        "Tab": "Tab",
        "Escape": "Esc",
        "Esc": "Esc",
        "Delete": "Delete",
        "Insert": "Insert",
        "Home": "Home",
        "End": "End",
        "Page_Up": "Page Up",
        "Page_Down": "Page Down",
        "Up": "Up",
        "Down": "Down",
        "Left": "Left",
        "Right": "Right",
        "Shift_L": "Left Shift",
        "Shift_R": "Right Shift",
        "Control_L": "Left Ctrl",
        "Control_R": "Right Ctrl",
        "Alt_L": "Left Alt",
        "Alt_R": "Right Alt",
        "Meta_L": "Left Cmd/Win",
        "Meta_R": "Right Cmd/Win",
        "Super_L": "Left Cmd/Win",
        "Super_R": "Right Cmd/Win",
        "Command": "Left Cmd/Win",
        "Option_L": "Left Alt",
        "Option_R": "Right Alt",
        "Caps_Lock": "Caps Lock",
        "Pause": "Pause",
        "Scroll_Lock": "Scroll Lock",
        "Num_Lock": "Num Lock",
        "Print": "Print Screen",
        "slash": "/",
        "backslash": "\\",
        "bracketleft": "[",
        "bracketright": "]",
        "semicolon": ";",
        "apostrophe": "'",
        "comma": ",",
        "period": ".",
        "grave": "`",
        "minus": "-",
        "equal": "=",
    }

    def __init__(
        self,
        parent: tk.Widget,
        keymap: Keymap,
        layer_index: int = 0,
        layout_db: Optional[LayoutDatabase] = None,
        on_exit: Optional[Callable[[], None]] = None,
    ) -> None:
        """Create the test-mode overlay.

        Args:
            parent: Tkinter parent widget.
            keymap: The active keymap model.
            layer_index: Layer to display programmed labels from. Defaults to 0.
            layout_db: Optional :class:`LayoutDatabase` instance.  A new one
                is created automatically when omitted.
            on_exit: Called when the user exits test mode.
        """
        super().__init__(parent)
        self.keymap = keymap
        self._layer_index = layer_index
        self._db = layout_db or LayoutDatabase()
        self.on_exit = on_exit

        self._pressed_keys: Set[str] = set()
        self._flash_after_ids: Dict[int, str] = {}
        self._key_items: Dict[int, int] = {}
        self._key_text_items: Dict[int, int] = {}
        self._key_secondary_items: Dict[int, int] = {}
        self._positions: List[Dict[str, object]] = []
        self._exiting = False

        self._setup_window()
        self._build_ui()
        self._load_layout()
        self._start_listener()

    # ------------------------------------------------------------------ #
    # Window / UI setup
    # ------------------------------------------------------------------ #

    def _setup_window(self) -> None:
        """Configure the Toplevel window (fullscreen / maximized)."""
        self.title("EasyKey — Test Mode")
        self.configure(background="#222222")

        if sys.platform == "darwin":
            self.attributes("-fullscreen", True)
        else:
            self.state("zoomed")

        self.protocol("WM_DELETE_WINDOW", self._do_exit)

    def _build_ui(self) -> None:
        """Create the canvas, exit button and status label."""
        self._canvas = tk.Canvas(
            self,
            bg="#222222",
            highlightthickness=0,
        )
        self._canvas.pack(fill=tk.BOTH, expand=True)

        # Exit button — persistently visible in top-right corner
        self._exit_btn = ttk.Button(
            self,
            text="Exit Test Mode",
            command=self._do_exit,
        )
        self._exit_btn.place(relx=1.0, x=-10, y=10, anchor=tk.NE)

        # Status label
        self._status = ttk.Label(
            self,
            text="Listening…",
            background="#222222",
            foreground="#cccccc",
        )
        self._status.place(relx=0.5, rely=0.05, anchor=tk.CENTER)

        # Local Escape binding (works regardless of pynput)
        self.bind("<Escape>", lambda _event: self._do_exit())

        # Fallback tkinter bindings when pynput is unavailable
        if not HAS_PYNPUT:
            self.focus_set()
            self.bind("<KeyPress>", self._on_tk_key_press)
            self.bind("<KeyRelease>", self._on_tk_key_release)

    def _load_layout(self) -> None:
        """Fetch keyboard positions from the DB and draw the layout."""
        kb = self._db.get_keyboard_by_name(self.keymap.keyboard_name)
        if kb:
            self._positions = self._db.get_key_positions(kb["id"])
        else:
            self._positions = []

        if not self._positions:
            self._canvas.create_text(
                self.winfo_screenwidth() // 2,
                self.winfo_screenheight() // 2,
                text="No layout data available for this keyboard.",
                fill="#888888",
                font=("Helvetica", 20),
            )
            return

        self._draw_keys()

    def _draw_keys(self) -> None:
        """Render keys on the canvas based on layout DB positions."""
        canvas_w = self.winfo_screenwidth()
        canvas_h = self.winfo_screenheight()

        max_x = max(p["x"] + p.get("width", 1) for p in self._positions)
        max_y = max(p["y"] + p.get("height", 1) for p in self._positions)

        margin = 100
        scale_x = (canvas_w - margin * 2) / max(max_x, 1)
        scale_y = (canvas_h - margin * 2) / max(max_y, 1)
        scale = min(scale_x, scale_y)

        offset_x = (canvas_w - max_x * scale) / 2
        offset_y = (canvas_h - max_y * scale) / 2 + 40  # Room for status

        for idx, pos in enumerate(self._positions):
            x = pos["x"] * scale + offset_x
            y = pos["y"] * scale + offset_y
            w = pos.get("width", 1) * scale
            h = pos.get("height", 1) * scale
            pad = 3

            rect = self._canvas.create_rectangle(
                x + pad,
                y + pad,
                x + w - pad,
                y + h - pad,
                fill="#333333",
                outline="#555555",
                width=2,
                tags=(f"key_{idx}",),
            )
            self._key_items[idx] = rect

            # Programmed label (upper text)
            binding = (
                self.keymap.get_binding(self._layer_index, idx)
                if idx < len(self.keymap.layers[self._layer_index].bindings)
                else None
            )
            label = binding.label if binding else ""

            text_id = self._canvas.create_text(
                x + w / 2,
                y + h / 2 - 10,
                text=label,
                fill="#eeeeee",
                font=("Helvetica", max(8, int(h / 5))),
                tags=(f"key_{idx}",),
            )
            self._key_text_items[idx] = text_id

            # Actual received key name (lower text), initially empty
            sec_id = self._canvas.create_text(
                x + w / 2,
                y + h / 2 + 10,
                text="",
                fill="#aaaaaa",
                font=("Helvetica", max(6, int(h / 7))),
                tags=(f"key_{idx}",),
            )
            self._key_secondary_items[idx] = sec_id

    # ------------------------------------------------------------------ #
    # Input handling
    # ------------------------------------------------------------------ #

    def _start_listener(self) -> None:
        """Start the global key listener (pynput) or local fallback."""
        if not HAS_PYNPUT:
            self._status.configure(
                text="Listening (local fallback — click window to focus)"
            )
            return

        try:
            self._listener = pynput_keyboard.Listener(
                on_press=self._on_pynput_press,
                on_release=self._on_pynput_release,
            )
            self._listener.start()
            self._status.configure(text="Listening (global)")
        except OSError as exc:
            if platform.system() == "Darwin":
                messagebox.showerror(
                    "Accessibility Required",
                    "Enable accessibility permissions in System Preferences "
                    "to use Test Mode.",
                )
            else:
                messagebox.showerror(
                    "Listener Error",
                    f"Could not start global key listener:\n{exc}",
                )
            self._do_exit()
        except Exception as exc:  # pragma: no cover
            messagebox.showerror(
                "Listener Error",
                f"Unexpected error starting key listener:\n{exc}",
            )
            self._do_exit()

    def _on_pynput_press(self, key: object) -> None:
        """pynput callback — dispatched to the main thread via ``after``."""
        name = self._normalize_pynput_key(key)
        self.after(0, lambda: self._handle_key_event(name, pressed=True))

    def _on_pynput_release(self, key: object) -> None:
        """pynput callback — dispatched to the main thread via ``after``."""
        name = self._normalize_pynput_key(key)
        self.after(0, lambda: self._handle_key_event(name, pressed=False))

    def _on_tk_key_press(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        """Fallback handler for tkinter ``<KeyPress>`` events."""
        name = self._normalize_tk_keysym(event.keysym)
        self._handle_key_event(name, pressed=True)

    def _on_tk_key_release(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        """Fallback handler for tkinter ``<KeyRelease>`` events."""
        name = self._normalize_tk_keysym(event.keysym)
        self._handle_key_event(name, pressed=False)

    @classmethod
    def _normalize_pynput_key(cls, key: object) -> str:
        """Convert a pynput key object to a normalised label string."""
        if isinstance(key, pynput_keyboard.Key):
            return cls._KEY_NAME_MAP.get(key.name, key.name.replace("_", " ").title())
        if isinstance(key, pynput_keyboard.KeyCode):
            if key.char:
                return key.char.upper()
            return str(key.vk) if key.vk is not None else "Unknown"
        return str(key)

    @classmethod
    def _normalize_tk_keysym(cls, keysym: str) -> str:
        """Convert a tkinter keysym to a normalised label string."""
        mapped = cls._KEY_NAME_MAP.get(keysym)
        if mapped is not None:
            return mapped
        if len(keysym) == 1:
            return keysym.upper()
        return keysym.replace("_", " ").title()

    # ------------------------------------------------------------------ #
    # Visual feedback
    # ------------------------------------------------------------------ #

    def _handle_key_event(self, name: str, pressed: bool) -> None:
        """Update the canvas for a key press or release."""
        if pressed:
            self._pressed_keys.add(name)
        else:
            self._pressed_keys.discard(name)

        matched_idx = self._find_key_index(name)
        if matched_idx is None:
            return

        self._update_key_visual(matched_idx, name, pressed)

    def _find_key_index(self, name: str) -> Optional[int]:
        """Find the visual key index that best matches *name*."""
        name_lower = name.lower()

        # 1. Exact match on programmed label
        for idx in range(len(self._positions)):
            binding = self.keymap.get_binding(self._layer_index, idx)
            if binding and binding.label.lower() == name_lower:
                return idx

        # 2. Exact match on position legend
        for idx, pos in enumerate(self._positions):
            legend = pos.get("legend", "")
            if legend and legend.lower() == name_lower:
                return idx

        # 3. Substring match on programmed label (only for multi-char names)
        if len(name_lower) > 1:
            for idx in range(len(self._positions)):
                binding = self.keymap.get_binding(self._layer_index, idx)
                if binding and name_lower in binding.label.lower():
                    return idx

        # 4. Substring match on legend
        if len(name_lower) > 1:
            for idx, pos in enumerate(self._positions):
                legend = pos.get("legend", "")
                if legend and name_lower in legend.lower():
                    return idx

        return None

    def _update_key_visual(self, idx: int, actual_name: str, pressed: bool) -> None:
        """Set canvas colours and labels for key *idx*."""
        rect_id = self._key_items.get(idx)
        sec_id = self._key_secondary_items.get(idx)
        if rect_id is None:
            return

        binding = (
            self.keymap.get_binding(self._layer_index, idx)
            if idx < len(self.keymap.layers[self._layer_index].bindings)
            else None
        )
        programmed = binding.label if binding else ""

        # Update the "actual received" label
        if sec_id is not None:
            self._canvas.itemconfigure(sec_id, text=actual_name if pressed else "")

        if pressed:
            # Cancel any old pending flash for this key
            old_after = self._flash_after_ids.pop(idx, None)
            if old_after is not None:
                try:
                    self.after_cancel(old_after)
                except tk.TclError:
                    pass

            programmed_norm = programmed.lower().strip()
            actual_norm = actual_name.lower().strip()

            if programmed_norm and programmed_norm != actual_norm:
                # Flash red, then switch to held-green after 500 ms
                self._canvas.itemconfigure(rect_id, fill="#cc0000")
                after_id = self.after(
                    500, lambda i=idx: self._canvas.itemconfigure(self._key_items[i], fill="#00cc00")
                )
                self._flash_after_ids[idx] = after_id
            else:
                self._canvas.itemconfigure(rect_id, fill="#00cc00")
        else:
            # Cancel pending red→green flash and return to idle colour
            after_id = self._flash_after_ids.pop(idx, None)
            if after_id is not None:
                try:
                    self.after_cancel(after_id)
                except tk.TclError:
                    pass
            self._canvas.itemconfigure(rect_id, fill="#333333")

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    def _do_exit(self) -> None:
        """Clean up listeners and scheduled callbacks, then exit."""
        if self._exiting:
            return
        self._exiting = True

        if HAS_PYNPUT and hasattr(self, "_listener"):
            try:
                self._listener.stop()
            except Exception:
                pass

        for after_id in list(self._flash_after_ids.values()):
            try:
                self.after_cancel(after_id)
            except Exception:
                pass
        self._flash_after_ids.clear()

        if self.on_exit is not None:
            self.on_exit()

        self.destroy()

    def destroy(self) -> None:
        """Override destroy to ensure the pynput listener is stopped."""
        if HAS_PYNPUT and hasattr(self, "_listener"):
            try:
                self._listener.stop()
            except Exception:
                pass
        super().destroy()
