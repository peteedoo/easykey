"""First-run onboarding wizard."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, Dict, List, Optional

from easykey.config import Config
from easykey.layouts.kle_parser import KLEParser

try:
    from easykey.detection import HIDScanner
except Exception:
    HIDScanner = None  # type: ignore


class FirstRunWizard(tk.Toplevel):
    """Modal three-step wizard for first-time users."""

    def __init__(
        self,
        parent: tk.Tk,
        config: Config,
        on_finish: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(parent)
        self.config = config
        self.on_finish = on_finish
        self.title("Welcome to EasyKey")
        self.geometry("700x500")
        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)

        self.selected_keyboard: Optional[Dict[str, Any]] = None
        self.selected_preset: str = "Blank"
        self._screen_index = 0
        self._screens: List[ttk.Frame] = []
        self._poll_job: Optional[str] = None
        self._demo_after: Optional[str] = None
        self._demo_pulse_job: Optional[str] = None
        self._demo_labels: List[ttk.Label] = []
        self._last_detected: List[Dict[str, Any]] = []
        self._demo_step = 0

        self.protocol("WM_DELETE_WINDOW", self._on_skip)

        self._build_ui()
        self._build_screens()
        self._show_screen(0)

    def _build_ui(self) -> None:
        self.container = ttk.Frame(self, padding=20)
        self.container.pack(fill=tk.BOTH, expand=True)

        self.btn_bar = ttk.Frame(self, padding=10)
        self.btn_bar.pack(side=tk.BOTTOM, fill=tk.X)

        self.back_btn = ttk.Button(self.btn_bar, text="Back", command=self._on_back)
        self.back_btn.pack(side=tk.LEFT, padx=4)

        self.next_btn = ttk.Button(self.btn_bar, text="Next", command=self._on_next)
        self.next_btn.pack(side=tk.LEFT, padx=4)

        ttk.Button(self.btn_bar, text="Skip wizard", command=self._on_skip).pack(
            side=tk.RIGHT, padx=4
        )

    def _build_screens(self) -> None:
        # ----- Screen 1: Keyboard detection -----
        self.screen1 = ttk.Frame(self.container)
        ttk.Label(
            self.screen1, text="Keyboard detected", font=("TkDefaultFont", 16)
        ).pack(pady=10)

        self._detect_status = ttk.Label(self.screen1, text="Scanning...")
        self._detect_status.pack(pady=4)

        self._keyboard_var = tk.StringVar()
        self._keyboard_combo = ttk.Combobox(
            self.screen1, textvariable=self._keyboard_var, state="readonly"
        )
        self._keyboard_combo.pack(pady=4)
        self._keyboard_combo.bind("<<ComboboxSelected>>", self._on_keyboard_selected)

        self._preview_canvas = tk.Canvas(
            self.screen1, width=300, height=100, bg="#f5f5f5"
        )
        self._preview_canvas.pack(pady=10)
        self._preview_canvas.create_text(
            150, 50, text="Preview will appear here", fill="#888888"
        )

        # ----- Screen 2: What is a layer? -----
        self.screen2 = ttk.Frame(self.container)
        ttk.Label(
            self.screen2, text="What is a layer?", font=("TkDefaultFont", 16)
        ).pack(pady=10)
        desc = (
            "Layers are like a stack of transparent sheets over your keyboard. "
            "Only the top sheet is active at a time. "
            "Layer 0 is the Base sheet — the one you always start on."
        )
        ttk.Label(self.screen2, text=desc, wraplength=500, justify=tk.CENTER).pack(
            pady=10
        )

        self._layer_canvas = tk.Canvas(
            self.screen2, width=200, height=120, bg="#f5f5f5", highlightthickness=0
        )
        self._layer_canvas.pack(pady=10)
        colors = ["#e0e0e0", "#c0c0c0", "#a0a0a0"]
        for i, c in enumerate(colors):
            self._layer_canvas.create_rectangle(
                20 + i * 10,
                80 - i * 15,
                180 + i * 10,
                100 - i * 15,
                fill=c,
                outline="#666666",
            )
        self._layer_canvas.create_text(100, 105, text="Base (Layer 0)", fill="#333333")

        ttk.Label(self.screen2, text="Choose a starter preset:").pack(pady=(20, 4))
        self._preset_var = tk.StringVar(value="Blank")
        presets = ttk.Combobox(
            self.screen2,
            textvariable=self._preset_var,
            values=["Blank", "QWERTY default"],
            state="readonly",
        )
        presets.pack()

        # ----- Screen 3: Try one remap -----
        self.screen3 = ttk.Frame(self.container)
        ttk.Label(
            self.screen3, text="Try one remap", font=("TkDefaultFont", 16)
        ).pack(pady=10)

        self._instruction_frame = ttk.Frame(self.screen3)
        self._instruction_frame.pack(pady=10)

        self._demo_canvas = tk.Canvas(
            self.screen3, width=200, height=120, bg="#f5f5f5", highlightthickness=0
        )
        self._demo_canvas.pack(pady=10)
        self._demo_key = self._demo_canvas.create_rectangle(
            60, 30, 140, 90, fill="#ffffff", outline="#cccccc", width=2
        )
        self._demo_label = self._demo_canvas.create_text(
            100, 60, text="A", font=("TkDefaultFont", 14)
        )
        self._demo_canvas.tag_bind(
            self._demo_key, "<Button-1>", lambda e: self._on_demo_key_click()
        )
        self._demo_canvas.tag_bind(
            self._demo_label, "<Button-1>", lambda e: self._on_demo_key_click()
        )

        self._demo_picker_frame = ttk.Frame(self.screen3)
        ttk.Label(self._demo_picker_frame, text="Select a new binding:").pack()
        self._demo_binding_var = tk.StringVar()
        self._demo_bindings = ttk.Combobox(
            self._demo_picker_frame,
            textvariable=self._demo_binding_var,
            values=["A", "B", "Enter", "Escape", "Space"],
            state="readonly",
        )
        self._demo_bindings.pack(pady=4)
        self._demo_bindings.bind(
            "<<ComboboxSelected>>", self._on_demo_binding_selected
        )

        self._demo_apply_btn = tk.Button(
            self.screen3,
            text="Apply",
            command=self._on_demo_apply,
            bg="#20b2aa",
            fg="white",
            font=("TkDefaultFont", 12, "bold"),
        )

        self._screens = [self.screen1, self.screen2, self.screen3]

    def _show_screen(self, index: int) -> None:
        for screen in self._screens:
            screen.pack_forget()
        self._screens[index].pack(fill=tk.BOTH, expand=True)
        self._screen_index = index

        self.back_btn.config(state="normal" if index > 0 else "disabled")
        if index == len(self._screens) - 1:
            self.next_btn.config(text="Finish", command=self._on_finish)
        else:
            self.next_btn.config(text="Next", command=self._on_next)

        if index == 0:
            self._start_detection_poll()
        else:
            self._stop_detection_poll()

        if index == 2:
            self._start_demo_sequence()
        else:
            self._stop_demo_sequence()

    # ------------------------------------------------------------------ #
    #  Detection polling
    # ------------------------------------------------------------------ #

    def _start_detection_poll(self) -> None:
        self._poll_keyboards()

    def _stop_detection_poll(self) -> None:
        if self._poll_job is not None:
            self.after_cancel(self._poll_job)
            self._poll_job = None

    def _poll_keyboards(self) -> None:
        keyboards = self._detect_keyboards()
        self._last_detected = keyboards
        if keyboards:
            self._detect_status.config(text=f"Found {len(keyboards)} keyboard(s)")
            self._keyboard_combo.config(values=[k["name"] for k in keyboards])
            if not self._keyboard_var.get() and keyboards:
                self._keyboard_var.set(keyboards[0]["name"])
                self.selected_keyboard = keyboards[0]
                self._render_preview(keyboards[0].get("kle_data", ""))
            self._keyboard_combo.config(state="readonly")
        else:
            self._detect_status.config(text="Plug in your keyboard...")
            self._keyboard_combo.config(values=[], state="disabled")
            self._preview_canvas.delete("all")
            self._preview_canvas.create_text(
                150, 50, text="No keyboard detected", fill="#888888"
            )
        self._poll_job = self.after(2000, self._poll_keyboards)

    def _detect_keyboards(self) -> List[Dict[str, Any]]:
        if HIDScanner is None:
            return []
        try:
            scanner = HIDScanner()
            if hasattr(scanner, "scan"):
                devices = scanner.scan()
            elif hasattr(scanner, "list_devices"):
                devices = scanner.list_devices()
            else:
                return []
            result: List[Dict[str, Any]] = []
            for d in devices:
                if isinstance(d, dict):
                    result.append(d)
                elif hasattr(d, "name"):
                    result.append(
                        {
                            "name": d.name,
                            "connection": getattr(d, "connection", "USB"),
                            "kle_data": getattr(d, "kle_data", ""),
                            "keyboard_info": d,
                        }
                    )
            return result
        except Exception:
            return []

    def _on_keyboard_selected(self, event: tk.Event) -> None:
        name = self._keyboard_var.get()
        for k in self._last_detected:
            if k["name"] == name:
                self.selected_keyboard = k
                self._render_preview(k.get("kle_data", ""))
                break

    def _render_preview(self, kle_data: str) -> None:
        self._preview_canvas.delete("all")
        if not kle_data:
            self._preview_canvas.create_text(
                150, 50, text="No preview available", fill="#888888"
            )
            return
        try:
            keys = KLEParser.parse(kle_data)
            positions = KLEParser.keys_to_positions(keys, scale=6.0)
            ox, oy = 10, 10
            for x, y, w, h, legend in positions:
                x1 = x + ox
                y1 = y + oy
                x2 = x1 + w - 1
                y2 = y1 + h - 1
                self._preview_canvas.create_rectangle(
                    x1, y1, x2, y2, fill="#ffffff", outline="#cccccc"
                )
        except Exception:
            self._preview_canvas.create_text(
                150, 50, text="Preview error", fill="#888888"
            )

    # ------------------------------------------------------------------ #
    #  Demo walkthrough
    # ------------------------------------------------------------------ #

    def _start_demo_sequence(self) -> None:
        self._demo_step = 0
        self._demo_labels = []
        self._demo_sequence()

    def _stop_demo_sequence(self) -> None:
        if self._demo_after is not None:
            self.after_cancel(self._demo_after)
            self._demo_after = None
        if self._demo_pulse_job is not None:
            self.after_cancel(self._demo_pulse_job)
            self._demo_pulse_job = None
        for lbl in self._demo_labels:
            lbl.destroy()
        self._demo_labels.clear()
        self._demo_picker_frame.pack_forget()
        self._demo_apply_btn.pack_forget()

    def _demo_sequence(self) -> None:
        steps = [
            "1. Find the pulsing key on your keyboard.",
            "2. Click it to open the binding picker.",
            "3. Choose a new key from the list.",
            "4. Click Apply to confirm your change.",
        ]
        if self._demo_step < len(steps):
            lbl = ttk.Label(self._instruction_frame, text=steps[self._demo_step])
            lbl.pack(anchor=tk.W, pady=2)
            self._demo_labels.append(lbl)
            self._demo_step += 1
            self._demo_after = self.after(1500, self._demo_sequence)
        else:
            self._pulse_demo_key()

    def _pulse_demo_key(self) -> None:
        if not self.winfo_exists():
            return
        current = self._demo_canvas.itemcget(self._demo_key, "outline")
        new_color = "#007aff" if current == "#cccccc" else "#cccccc"
        self._demo_canvas.itemconfig(self._demo_key, outline=new_color)
        self._demo_pulse_job = self.after(500, self._pulse_demo_key)

    def _on_demo_key_click(self) -> None:
        if self._demo_pulse_job is not None:
            self.after_cancel(self._demo_pulse_job)
            self._demo_pulse_job = None
        self._demo_canvas.itemconfig(self._demo_key, outline="#007aff")
        self._demo_picker_frame.pack(pady=10)

    def _on_demo_binding_selected(self, event: tk.Event) -> None:
        self._demo_apply_btn.pack(pady=10)

    def _on_demo_apply(self) -> None:
        self._on_finish()

    # ------------------------------------------------------------------ #
    #  Navigation
    # ------------------------------------------------------------------ #

    def _on_next(self) -> None:
        if self._screen_index < len(self._screens) - 1:
            self._show_screen(self._screen_index + 1)

    def _on_back(self) -> None:
        if self._screen_index > 0:
            self._show_screen(self._screen_index - 1)

    def _on_skip(self) -> None:
        self._on_finish()

    def _on_finish(self) -> None:
        self.selected_preset = self._preset_var.get()
        self.config.set("wizard_completed", True)
        self._stop_detection_poll()
        self._stop_demo_sequence()
        self.destroy()
        if self.on_finish:
            self.on_finish()
