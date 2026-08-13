"""Low-level VIA-protocol HID client."""

from __future__ import annotations

from typing import List, Optional

from easykey.detection.hid_scanner import KeyboardInfo


class ViaError(Exception):
    """Raised when a VIA HID transaction fails after retries."""

    pass


class ViaClient:
    """Communicates with a keyboard running VIA-compatible firmware.

    All HID reports are 64 bytes.  The first byte is the command/report
    identifier; remaining bytes are payload.  Timeouts and retries are
    applied automatically (max 3 attempts).

    Args:
        keyboard_info: Descriptor for the target keyboard.
    """

    _REPORT_SIZE = 64
    _TIMEOUT_MS = 1000
    _MAX_RETRIES = 3

    def __init__(self, keyboard_info: KeyboardInfo) -> None:
        self._info = keyboard_info
        self._dev: Optional[object] = None
        self._hid: Optional[type] = None

        try:
            import hid  # type: ignore[import-untyped]

            self._hid = hid
        except ImportError as exc:
            raise ViaError(
                "The 'hid' package is not installed. "
                "Install it with: pip install hid"
            ) from exc

        self._open()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _open(self) -> None:
        """Open the HID device using the path stored in :attr:`_info`."""
        if self._hid is None:
            raise ViaError("hid package is unavailable")

        self._dev = self._hid.device()
        path_bytes = (
            self._info.path.encode("utf-8", errors="replace")
            if isinstance(self._info.path, str)
            else self._info.path
        )
        try:
            self._dev.open_path(path_bytes)
            self._dev.set_nonblocking(0)
        except Exception as exc:
            raise ViaError(
                f"Failed to open HID device at path {self._info.path}: {exc}"
            ) from exc

    def close(self) -> None:
        """Release the HID device handle."""
        if self._dev is not None:
            try:
                self._dev.close()
            except Exception:
                pass
            self._dev = None

    def __enter__(self) -> "ViaClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _send(self, report: bytes) -> None:
        """Write a report to the device."""
        if self._dev is None:
            raise ViaError("HID device is not open")
        padded = report.ljust(self._REPORT_SIZE, b"\x00")
        self._dev.write(padded)

    def _read(self) -> bytes:
        """Read a report from the device."""
        if self._dev is None:
            raise ViaError("HID device is not open")
        data = self._dev.read(self._REPORT_SIZE, timeout_ms=self._TIMEOUT_MS)
        if not data:
            return b""
        # hidapi may return a list of ints; normalise to bytes
        if isinstance(data, list):
            return bytes(data)
        return bytes(data)

    def _transact(self, report: bytes) -> bytes:
        """Send a report and return the response with automatic retries."""
        last_error: Optional[Exception] = None
        for attempt in range(1, self._MAX_RETRIES + 1):
            try:
                self._send(report)
                response = self._read()
                if response:
                    return response
            except Exception as exc:
                last_error = exc
                # Brief back-off before retry
                import time

                time.sleep(0.05 * attempt)

        raise ViaError(
            f"HID transaction failed after {self._MAX_RETRIES} attempts. "
            f"Last error: {last_error}"
        )

    # ------------------------------------------------------------------
    # Protocol commands
    # ------------------------------------------------------------------

    def get_protocol_version(self) -> int:
        """Request the VIA protocol version (report ID ``0x01``).

        Returns:
            The protocol version as an integer (e.g. ``9`` for VIA v9).
        """
        response = self._transact(bytes([0x01] + [0x00] * 63))
        if len(response) < 3:
            raise ViaError("Malformed protocol version response")
        # Version is typically encoded as major<<8 | minor in bytes 1-2
        version = (response[1] << 8) | response[2]
        return version

    def get_keyboard_value(self, command: int) -> bytes:
        """Read a keyboard value (report ID ``0x02``).

        Args:
            command: Keyboard-value command byte.

        Returns:
            Raw payload bytes from the response (excluding report ID).
        """
        report = bytes([0x02, command & 0xFF]) + bytes(62)
        response = self._transact(report)
        if len(response) < 2:
            raise ViaError("Malformed get_keyboard_value response")
        return bytes(response[2:])

    def set_keyboard_value(self, command: int, value: int) -> None:
        """Write a keyboard value.

        The same report ID ``0x02`` is reused with the value embedded in
        the payload.

        Args:
            command: Keyboard-value command byte.
            value: Value to write.
        """
        report = bytes([0x02, command & 0xFF, value & 0xFF]) + bytes(61)
        self._transact(report)

    def get_keycode(self, layer: int, row: int, col: int) -> int:
        """Read a single keycode from the dynamic keymap (report ID ``0x03``).

        Args:
            layer: Layer index.
            row: Matrix row.
            col: Matrix column.

        Returns:
            The 16-bit keycode stored at the requested position.
        """
        report = bytes([0x03, layer & 0xFF, row & 0xFF, col & 0xFF]) + bytes(60)
        response = self._transact(report)
        if len(response) < 6:
            raise ViaError("Malformed get_keycode response")
        keycode = (response[4] << 8) | response[5]
        return keycode

    def set_keycode(self, layer: int, row: int, col: int, keycode: int) -> None:
        """Write a single keycode to the dynamic keymap (report ID ``0x04``).

        Args:
            layer: Layer index.
            row: Matrix row.
            col: Matrix column.
            keycode: 16-bit keycode to store.
        """
        report = bytes(
            [
                0x04,
                layer & 0xFF,
                row & 0xFF,
                col & 0xFF,
                (keycode >> 8) & 0xFF,
                keycode & 0xFF,
            ]
        ) + bytes(58)
        self._transact(report)

    def read_keymap(
        self, rows: int, cols: int, num_layers: int
    ) -> List[List[List[int]]]:
        """Read the entire dynamic keymap layer-by-layer, row-by-row.

        Args:
            rows: Number of matrix rows.
            cols: Number of matrix columns.
            num_layers: Number of layers to read.

        Returns:
            Three-dimensional list shaped ``[layer][row][col]``.
        """
        keymap: List[List[List[int]]] = []
        for layer in range(num_layers):
            layer_data: List[List[int]] = []
            for r in range(rows):
                row_data: List[int] = []
                for c in range(cols):
                    row_data.append(self.get_keycode(layer, r, c))
                layer_data.append(row_data)
            keymap.append(layer_data)
        return keymap

    def write_keymap(self, keymap_data: List[List[List[int]]]) -> bool:
        """Write the entire dynamic keymap and verify with a read-back.

        Args:
            keymap_data: Three-dimensional list shaped ``[layer][row][col]``.

        Returns:
            ``True`` when the read-back matches the written data.
        """
        if not keymap_data:
            raise ViaError("keymap_data is empty")

        num_layers = len(keymap_data)
        rows = len(keymap_data[0])
        cols = len(keymap_data[0][0])

        for layer in range(num_layers):
            for r in range(rows):
                for c in range(cols):
                    self.set_keycode(layer, r, c, keymap_data[layer][r][c])

        # Read-back verification
        read_back = self.read_keymap(rows, cols, num_layers)
        return read_back == keymap_data

    def get_keyboard_name(self) -> str:
        """Query the keyboard name string via report ID ``0x0D``.

        Returns:
            The decoded name, or ``"Unknown"`` if the query fails.
        """
        try:
            response = self._transact(bytes([0x0D] + [0x00] * 63))
            if not response:
                return "Unknown"
            # Payload starts after the report-id / command byte
            payload = bytes(response[1:])
            # Trim at first null byte
            null_pos = payload.find(b"\x00")
            if null_pos != -1:
                payload = payload[:null_pos]
            name = payload.decode("utf-8", errors="replace").strip()
            return name or "Unknown"
        except ViaError:
            return "Unknown"
