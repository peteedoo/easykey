"""Vial-protocol HID client with unlock support."""

from __future__ import annotations

from typing import List

from easykey.detection.hid_scanner import KeyboardInfo
from easykey.detection.via_client import ViaClient, ViaError


class VialClient(ViaClient):
    """Communicates with a keyboard running Vial firmware.

    Inherits all VIA commands from :class:`ViaClient` and adds the Vial
    *unlock* sequence required to access extended features such as up to
    32 layers.

    Args:
        keyboard_info: Descriptor for the target keyboard.
    """

    _VIAL_REPORT_ID = 0xFE
    _VIAL_UNLOCK_MAGIC = bytes([0x56, 0x49, 0x41, 0x4C])  # "VIAL"
    _MAX_LAYERS = 32
    _VIA_MAX_LAYERS = 4

    def __init__(self, keyboard_info: KeyboardInfo) -> None:
        super().__init__(keyboard_info)
        self._unlocked = False

    # ------------------------------------------------------------------
    # Vial unlock
    # ------------------------------------------------------------------

    def unlock(self) -> bool:
        """Send the Vial unlock magic sequence.

        The keyboard must be in an unlockable state (some devices require a
        physical key combination to be held).

        Returns:
            ``True`` if the unlock handshake succeeded.
        """
        report = bytes([self._VIAL_REPORT_ID]) + self._VIAL_UNLOCK_MAGIC + bytes(59)
        try:
            response = self._transact(report)
            # A positive response contains the unlock report ID echoed back
            if response and response[0] == self._VIAL_REPORT_ID:
                self._unlocked = True
                return True
        except ViaError:
            pass
        self._unlocked = False
        return False

    def is_unlocked(self) -> bool:
        """Return whether the extended Vial command set is unlocked."""
        return self._unlocked

    # ------------------------------------------------------------------
    # Keymap overrides
    # ------------------------------------------------------------------

    def read_keymap(
        self, rows: int, cols: int, num_layers: int
    ) -> List[List[List[int]]]:
        """Read the dynamic keymap, supporting up to 32 layers when unlocked.

        If the device has not been unlocked, layer count is clamped to the
        standard VIA maximum of 4.

        Args:
            rows: Number of matrix rows.
            cols: Number of matrix columns.
            num_layers: Desired number of layers (clamped if necessary).

        Returns:
            Three-dimensional list shaped ``[layer][row][col]``.
        """
        max_layers = self._MAX_LAYERS if self._unlocked else self._VIA_MAX_LAYERS
        effective_layers = min(num_layers, max_layers)
        return super().read_keymap(rows, cols, effective_layers)

    def write_keymap(self, keymap_data: List[List[List[int]]]) -> bool:
        """Write the dynamic keymap, supporting up to 32 layers when unlocked.

        If the device has not been unlocked, layer count is clamped to the
        standard VIA maximum of 4 before writing.

        Args:
            keymap_data: Three-dimensional list shaped ``[layer][row][col]``.

        Returns:
            ``True`` when the read-back matches the written data.
        """
        if not keymap_data:
            raise ViaError("keymap_data is empty")

        max_layers = self._MAX_LAYERS if self._unlocked else self._VIA_MAX_LAYERS
        if len(keymap_data) > max_layers:
            keymap_data = keymap_data[:max_layers]

        return super().write_keymap(keymap_data)
