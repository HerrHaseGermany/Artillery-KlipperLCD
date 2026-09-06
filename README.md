# Artillery-KlipperLCD

Standalone touchscreen service and TFT firmware package for Artillery Sidewinder X4 printers running Klipper.

This repository combines the display service, the TJC/Nextion-compatible TFT firmware, automatic firmware flashing, a systemd service, and Moonraker/Mainsail Update Manager integration in one installable package.

> **Status:** tested on an Artillery X4 setup using a BTT Manta M5P + CB2 and the original-style 4.3-inch TJC display connected through `/dev/ttyS2` at 115200 baud.

## Features

- Klipper/Moonraker touchscreen service for the Artillery X4 display
- Bundled TFT firmware: `firmware/ArtilleryX4KlipperScreen.tft`
- Automatic TFT flashing on first install
- Automatic TFT update only when the firmware file actually changes
- SHA-256 based firmware state tracking
- Automatic installation of the Nextion/TJC upload tooling
- Compatibility fixes for the `nextion-fw-upload` Python uploader used on the CB2 image
- systemd service: `KlipperLCD.service`
- Moonraker / Mainsail Update Manager integration
- Standalone package: no separate `/home/biqu/ArtilleryScreen` installation is required
- Python 3.9+

## Supported / tested hardware

The current installer intentionally targets the hardware and system layout used during development:

- Artillery Sidewinder X4 series
- BTT Manta M5P
- BTT CB2
- TJC display compatible with `TJC4827X243_011C`
- Display UART: `/dev/ttyS2`
- UART baud rate: `115200`
- Klipper + Moonraker + Mainsail
- standard Klipper data directory: `~/printer_data`

Other machines may work, but paths, UART device, screen firmware, bed geometry, or individual screen functions may require changes.

## Installation

On a fresh, compatible printer:

```bash
cd ~
git clone https://github.com/HerrHaseGermany/Artillery-KlipperLCD.git KlipperLCD
cd KlipperLCD
sudo ./install.sh
