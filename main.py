#!/usr/bin/env python3
"""Compatibility launcher for systems still using KlipperLCD.service."""

import sys


sys.path.insert(0, "/home/biqu/ArtilleryScreen/src")

from artillery_screen.app import main


if __name__ == "__main__":
    main()
