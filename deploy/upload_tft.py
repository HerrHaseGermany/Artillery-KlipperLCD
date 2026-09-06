#!/usr/bin/env python3
"""Upload a compiled TJC/Nextion TFT file over a serial connection."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Iterable, Optional, Tuple

import serial


TERMINATOR = b"\xff\xff\xff"
DEFAULT_BAUDS = (115200, 9600, 19200, 38400, 57600, 230400)


def read_until_idle(port: serial.Serial, timeout: float) -> bytes:
    deadline = time.monotonic() + timeout
    result = bytearray()
    while time.monotonic() < deadline:
        waiting = port.in_waiting
        if waiting:
            result.extend(port.read(waiting))
            deadline = time.monotonic() + 0.15
        else:
            time.sleep(0.01)
    return bytes(result)


def parse_connect_response(response: bytes) -> Tuple[Optional[str], Optional[int]]:
    """Extract model and flash size from a ``comok`` response when available."""
    text = response.replace(b"\x00", b"").replace(b"\xff", b"").decode(
        "ascii", errors="ignore"
    )
    marker = text.find("comok")
    if marker < 0:
        return None, None
    fields = text[marker:].split(",")
    model = fields[2].strip() if len(fields) > 2 else None
    flash_size = None
    if len(fields) > 6:
        try:
            flash_size = int(fields[6].strip())
        except ValueError:
            pass
    return model, flash_size


def connect(device: str, bauds: Iterable[int]) -> Tuple[serial.Serial, int, bytes]:
    for baud in bauds:
        port = serial.Serial(
            device,
            baudrate=baud,
            timeout=0,
            write_timeout=3,
            exclusive=True,
        )
        try:
            port.reset_input_buffer()
            port.write(b"\x00" + TERMINATOR + b"connect" + TERMINATOR)
            port.flush()
            response = read_until_idle(port, 0.8)
            if b"comok" in response:
                return port, baud, response
        except Exception:
            port.close()
            raise
        port.close()
    raise RuntimeError("Display did not answer 'connect' at any configured baud rate")


def wait_for_ack(port: serial.Serial, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    received = bytearray()
    while time.monotonic() < deadline:
        waiting = port.in_waiting
        if waiting:
            received.extend(port.read(waiting))
            if b"\x05" in received:
                return
        else:
            time.sleep(0.005)
    raise TimeoutError("Display did not acknowledge the upload block with 0x05")


def upload(path: Path, device: str, download_baud: int) -> None:
    file_size = path.stat().st_size
    if file_size <= 0:
        raise ValueError("TFT file is empty")

    port, current_baud, response = connect(device, DEFAULT_BAUDS)
    model, flash_size = parse_connect_response(response)
    print(
        "Connected: device=%s baud=%d model=%s flash=%s"
        % (device, current_baud, model or "unknown", flash_size or "unknown"),
        flush=True,
    )
    if flash_size is not None and file_size > flash_size:
        port.close()
        raise ValueError(
            "TFT file (%d bytes) exceeds display flash (%d bytes)"
            % (file_size, flash_size)
        )

    port.reset_input_buffer()
    command = "whmi-wri %d,%d,0" % (file_size, download_baud)
    port.write(command.encode("ascii") + TERMINATOR)
    port.flush()
    time.sleep(0.08)
    port.baudrate = download_baud
    wait_for_ack(port, 2.0)

    sent = 0
    with path.open("rb") as handle:
        while True:
            block = handle.read(4096)
            if not block:
                break
            port.write(block)
            port.flush()
            wait_for_ack(port, 5.0)
            sent += len(block)
            percent = sent * 100.0 / file_size
            print("\rUploading: %6.2f%%" % percent, end="", flush=True)
    print("\nUpload completed: %d bytes" % sent, flush=True)
    port.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("device")
    parser.add_argument("--download-baud", type=int, default=115200)
    args = parser.parse_args()

    try:
        upload(args.file.expanduser().resolve(), args.device, args.download_baud)
    except Exception as exc:
        print("Upload failed: %s" % exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
