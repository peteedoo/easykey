"""HID device scanning for VIA/Vial compatible keyboards."""

from __future__ import annotations

import time
import warnings
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class KeyboardInfo:
    """Metadata for a detected VIA/Vial compatible keyboard.

    Attributes:
        name: Human-readable product name from the HID descriptor.
        vendor_id: USB vendor identifier.
        product_id: USB product identifier.
        usage_page: HID usage page (expected 0xFF60 for VIA/Vial).
        usage: HID usage (0x0001 for VIA, 0x0061 for Vial).
        path: Platform-specific HID path string (required for ``open_path``).
        protocol: Detected protocol variant (``"via"`` or ``"vial"``).
    """

    name: str
    vendor_id: int
    product_id: int
    usage_page: int
    usage: int
    path: str
    protocol: str


class HIDScanner:
    """Scans USB HID devices for VIA/Vial compatible keyboards.

    Uses the ``hid`` package (hidapi CFFI wrapper).  If the package is not
    installed the scanner degrades gracefully and emits warnings.
    """

    _VIA_USAGE_PAGE = 0xFF60
    _VIA_USAGE = 0x0001
    _VIAL_USAGE = 0x0061

    def __init__(self) -> None:
        self._hid: Optional[type] = None
        try:
            import hid  # type: ignore[import-untyped]

            self._hid = hid
        except ImportError:
            warnings.warn(
                "The 'hid' package is not installed. HID scanning will be unavailable. "
                "Install it with: pip install hid",
                RuntimeWarning,
                stacklevel=2,
            )

    def scan(self) -> List[KeyboardInfo]:
        """Enumerate USB HID devices and return all VIA/Vial compatible keyboards.

        Filters on usage page ``0xFF60`` and usage ``0x0001`` (VIA) or
        ``0x0061`` (Vial).

        Returns:
            A list of :class:`KeyboardInfo` objects, one per compatible device.
        """
        if self._hid is None:
            warnings.warn(
                "hid package unavailable; returning empty scan results.",
                RuntimeWarning,
                stacklevel=2,
            )
            return []

        results: List[KeyboardInfo] = []
        try:
            devices = self._hid.enumerate()
        except Exception as exc:  # pragma: no cover
            warnings.warn(f"HID enumeration failed: {exc}", RuntimeWarning, stacklevel=2)
            return []

        for dev in devices:
            usage_page = dev.get("usage_page", 0)
            usage = dev.get("usage", 0)
            if usage_page != self._VIA_USAGE_PAGE:
                continue
            if usage not in (self._VIA_USAGE, self._VIAL_USAGE):
                continue

            protocol = "vial" if usage == self._VIAL_USAGE else "via"
            raw_path = dev.get("path", b"")
            path_str = raw_path.decode("utf-8", errors="replace") if isinstance(raw_path, bytes) else str(raw_path)

            info = KeyboardInfo(
                name=dev.get("product_string") or "Unknown Keyboard",
                vendor_id=dev.get("vendor_id", 0),
                product_id=dev.get("product_id", 0),
                usage_page=usage_page,
                usage=usage,
                path=path_str,
                protocol=protocol,
            )
            results.append(info)

        return results

    def wait_for_keyboard(self, poll_interval: float = 2.0) -> Optional[KeyboardInfo]:
        """Blocking poll until a compatible keyboard appears.

        Args:
            poll_interval: Seconds to sleep between scan attempts.

        Returns:
            The first detected :class:`KeyboardInfo`, or ``None`` if the
            scanner is unavailable.
        """
        if self._hid is None:
            warnings.warn(
                "hid package unavailable; cannot wait for keyboard.",
                RuntimeWarning,
                stacklevel=2,
            )
            return None

        while True:
            found = self.scan()
            if found:
                return found[0]
            time.sleep(poll_interval)

    def detect_protocol(self, keyboard_info: KeyboardInfo) -> str:
        """Query the keyboard via HID report ID ``0x01`` to confirm protocol.

        If the device usage already indicates Vial, that is preferred.
        Otherwise a brief HID exchange is performed and VIA is assumed on
        success.

        Args:
            keyboard_info: Target keyboard to probe.

        Returns:
            ``"via"`` or ``"vial"``.

        Raises:
            RuntimeError: If the ``hid`` package is unavailable.
        """
        if self._hid is None:
            raise RuntimeError("hid package is unavailable")

        if keyboard_info.usage == self._VIAL_USAGE:
            return "vial"

        dev = self._hid.device()
        try:
            path_bytes = (
                keyboard_info.path.encode("utf-8", errors="replace")
                if isinstance(keyboard_info.path, str)
                else keyboard_info.path
            )
            dev.open_path(path_bytes)
            dev.set_nonblocking(0)

            # Report ID 0x01 -> protocol version query
            report = bytes([0x01] + [0x00] * 63)
            dev.write(report)

            response = dev.read(64, timeout_ms=1000)
            if response and len(response) >= 3:
                # Valid response received; treat as VIA since usage was 0x0001
                return "via"

            return keyboard_info.protocol
        except Exception:
            return keyboard_info.protocol
        finally:
            try:
                dev.close()
            except Exception:
                pass
