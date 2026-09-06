#!/usr/bin/env python3
"""Launcher for Artillery KlipperLCD."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from artillery_screen.app import main


if __name__ == "__main__":
    main()
