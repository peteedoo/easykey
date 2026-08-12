#!/usr/bin/env python3
"""EasyKey entry point."""

import sys
from pathlib import Path

# Ensure easykey package is importable when running from source
sys.path.insert(0, str(Path(__file__).parent))

from easykey.ui.app import EasyKeyApp


def main() -> None:
    app = EasyKeyApp()
    app.run()


if __name__ == "__main__":
    main()
