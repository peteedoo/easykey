"""Unit tests for KLE parser."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from easykey.layouts.kle_parser import KLEParser


def test_parse_simple():
    kle = json.dumps([["Q", "W", "E"], ["A", "S", "D"]])
    keys = KLEParser.parse(kle)
    assert len(keys) == 6
    assert keys[0].legend == "Q"
    assert keys[0].x == 0.0
    assert keys[0].y == 0.0
    assert keys[3].legend == "A"
    assert keys[3].y == 1.0


def test_parse_with_offsets():
    kle = json.dumps([[{"x": 1}, "Tab", "Q"]])
    keys = KLEParser.parse(kle)
    assert len(keys) == 2
    assert keys[0].x == 1.0
    assert keys[1].x == 2.0


def test_keys_to_positions():
    kle = json.dumps([["Q", "W"]])
    keys = KLEParser.parse(kle)
    positions = KLEParser.keys_to_positions(keys, scale=50)
    assert positions[0] == (0.0, 0.0, 50.0, 50.0, "Q")
    assert positions[1] == (50.0, 0.0, 50.0, 50.0, "W")


if __name__ == "__main__":
    test_parse_simple()
    test_parse_with_offsets()
    test_keys_to_positions()
    print("All KLE parser tests passed.")
