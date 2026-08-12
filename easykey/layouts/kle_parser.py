"""Keyboard Layout Editor (KLE) JSON parser."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple


class KLEKey:
    """Represents a single key parsed from KLE format."""

    def __init__(
        self,
        x: float,
        y: float,
        width: float = 1.0,
        height: float = 1.0,
        legend: str = "",
    ):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.legend = legend

    def __repr__(self) -> str:
        return f"KLEKey({self.legend!r}, x={self.x}, y={self.y})"


class KLEParser:
    """Parses KLE raw JSON format into a list of keys with canvas coordinates."""

    @staticmethod
    def parse(kle_raw: str) -> List[KLEKey]:
        data = json.loads(kle_raw)
        keys: List[KLEKey] = []
        current_x = 0.0
        current_y = 0.0
        default_w = 1.0
        default_h = 1.0

        for row in data:
            if not isinstance(row, list):
                continue
            current_x = 0.0
            default_w = 1.0
            default_h = 1.0
            for item in row:
                if isinstance(item, dict):
                    # Metadata or key properties
                    if "x" in item:
                        current_x += item["x"]
                    if "y" in item:
                        current_y += item["y"]
                    if "w" in item:
                        default_w = item["w"]
                    if "h" in item:
                        default_h = item["h"]
                    continue

                # item is a string (key legend)
                legend = str(item)
                key = KLEKey(
                    x=current_x,
                    y=current_y,
                    width=default_w,
                    height=default_h,
                    legend=legend,
                )
                keys.append(key)
                current_x += default_w
                # Don't reset defaults here — they persist until next dict item or row
            current_y += 1.0

        return keys

    @staticmethod
    def keys_to_positions(
        keys: List[KLEKey], scale: float = 50.0
    ) -> List[Tuple[float, float, float, float, str]]:
        """Convert KLEKeys to (x, y, width, height, legend) tuples scaled for canvas."""
        return [
            (k.x * scale, k.y * scale, k.width * scale, k.height * scale, k.legend)
            for k in keys
        ]
