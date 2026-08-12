"""High-level firmware router that bridges HID clients to EasyKey models."""

from __future__ import annotations

import sqlite3
from typing import Dict, List, Optional

from easykey.detection.hid_scanner import KeyboardInfo
from easykey.detection.via_client import ViaClient
from easykey.detection.vial_client import VialClient
from easykey.layouts.database import LayoutDatabase
from easykey.models.keymap import KeyBinding, Keymap, Layer


class FirmwareRouter:
    """Routes keymap operations to the correct protocol client.

    Automatically instantiates :class:`ViaClient` or :class:`VialClient`
    based on the keyboard's detected protocol, reads/writes full keymaps,
    and populates :class:`~easykey.models.keymap.Keymap` objects with
    labels from the :class:`~easykey.layouts.database.LayoutDatabase`.

    Args:
        keyboard_info: Detected keyboard descriptor.
        layout_db: Optional ``LayoutDatabase`` instance.  If omitted, a
            default database is created.
    """

    def __init__(
        self,
        keyboard_info: KeyboardInfo,
        layout_db: Optional[LayoutDatabase] = None,
    ) -> None:
        self._info = keyboard_info
        self._layout_db = layout_db or LayoutDatabase()
        self._client: Optional[ViaClient] = None
        self._keycode_cache: Optional[Dict[int, Dict[str, str]]] = None

    # ------------------------------------------------------------------
    # Client management
    # ------------------------------------------------------------------

    @property
    def client(self) -> ViaClient:
        """Return the appropriate HID client for this keyboard.

        Vial keyboards receive a :class:`VialClient`; all others get a
        plain :class:`ViaClient`.
        """
        if self._client is None:
            if self._info.protocol == "vial":
                self._client = VialClient(self._info)
            else:
                self._client = ViaClient(self._info)
        return self._client

    def close(self) -> None:
        """Release the underlying HID client."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> "FirmwareRouter":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Keycode label cache
    # ------------------------------------------------------------------

    def _load_keycode_cache(self) -> Dict[int, Dict[str, str]]:
        """Build a code -> {name, label, category} mapping from the DB."""
        cache: Dict[int, Dict[str, str]] = {}
        with sqlite3.connect(self._layout_db.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT code, name, label, category FROM keycodes"
            )
            for row in cur.fetchall():
                cache[int(row["code"])] = {
                    "name": row["name"] or "",
                    "label": row["label"] or "",
                    "category": row["category"] or "standard",
                }
        return cache

    def _lookup_label(self, keycode: int) -> tuple[str, str, str]:
        """Return (label, name, category) for a keycode, using the cache."""
        if self._keycode_cache is None:
            self._keycode_cache = self._load_keycode_cache()
        entry = self._keycode_cache.get(keycode)
        if entry:
            return entry["label"], entry["name"], entry["category"]
        # Fallback: raw hex label
        return f"0x{keycode:04X}", f"KC_{keycode:04X}", "standard"

    # ------------------------------------------------------------------
    # Keyboard geometry discovery
    # ------------------------------------------------------------------

    def _discover_geometry(self) -> tuple[int, int, int, int]:
        """Return (rows, cols, num_keys, max_layers) for the connected keyboard.

        The layout database is queried first using the keyboard name.  If no
        record exists, conservative defaults are returned.
        """
        name = self.client.get_keyboard_name()
        kb_record = self._layout_db.get_keyboard_by_name(name)

        if kb_record:
            rows = max(kb_record.get("rows") or 4, 1)
            cols = max(kb_record.get("cols") or 12, 1)
            num_keys = max(kb_record.get("num_keys") or (rows * cols), 1)
        else:
            rows, cols = 4, 12
            num_keys = rows * cols

        max_layers = 32 if isinstance(self.client, VialClient) else 4
        return rows, cols, num_keys, max_layers

    # ------------------------------------------------------------------
    # Keymap I/O
    # ------------------------------------------------------------------

    def read_full_keymap(self) -> Keymap:
        """Read the complete keymap from the keyboard and return a :class:`Keymap`.

        Layers are populated with :class:`KeyBinding` instances whose labels
        are resolved through the :class:`LayoutDatabase`.

        Returns:
            A fully populated :class:`~easykey.models.keymap.Keymap`.
        """
        rows, cols, num_keys, max_layers = self._discover_geometry()

        keymap_data = self.client.read_keymap(rows, cols, max_layers)
        actual_layers = len(keymap_data)

        keymap = Keymap(keyboard_name=self._info.name, num_keys=num_keys)

        for layer_idx, layer_matrix in enumerate(keymap_data):
            layer_name = f"Layer {layer_idx}"
            layer = Layer(index=layer_idx, name=layer_name)

            # Flatten row-major matrix into binding list
            bindings: List[KeyBinding] = []
            for row in layer_matrix:
                for keycode in row:
                    label, name, category = self._lookup_label(keycode)
                    bindings.append(
                        KeyBinding(
                            keycode=keycode,
                            label=label,
                            secondary_label=name,
                            category=category,
                        )
                    )

            # Pad or truncate to num_keys if geometry is mismatched
            if len(bindings) < num_keys:
                bindings += [
                    KeyBinding(keycode=0, label="", category="noop")
                    for _ in range(num_keys - len(bindings))
                ]
            elif len(bindings) > num_keys:
                bindings = bindings[:num_keys]

            layer.bindings = bindings
            keymap.layers.append(layer)

        return keymap

    def write_full_keymap(self, keymap: Keymap) -> bool:
        """Write a :class:`Keymap` back to the keyboard.

        The in-memory bindings are converted back into the layered
        row-major format expected by the firmware, then written and
        verified with a read-back.

        Args:
            keymap: The keymap to persist.

        Returns:
            ``True`` when the read-back matches exactly.
        """
        rows, cols, _num_keys, _max_layers = self._discover_geometry()

        keymap_data: List[List[List[int]]] = []
        for layer in keymap.layers:
            layer_matrix: List[List[int]] = []
            idx = 0
            for _r in range(rows):
                row_data: List[int] = []
                for _c in range(cols):
                    if idx < len(layer.bindings):
                        row_data.append(layer.bindings[idx].keycode)
                    else:
                        row_data.append(0)
                    idx += 1
                layer_matrix.append(row_data)
            keymap_data.append(layer_matrix)

        return self.client.write_keymap(keymap_data)

    # ------------------------------------------------------------------
    # v2 feature stubs
    # ------------------------------------------------------------------

    def supports_qmk(self) -> bool:
        """Return whether QMK-specific features are available.

        .. note::
            This is a v2 stub and always returns ``False``.
        """
        return False

    def supports_kanata(self) -> bool:
        """Return whether Kanata firmware is supported.

        .. note::
            This is a v2 stub and always returns ``False``.
        """
        return False

    def supports_karabiner(self) -> bool:
        """Return whether Karabiner-Elements integration is available.

        .. note::
            This is a v2 stub and always returns ``False``.
        """
        return False
