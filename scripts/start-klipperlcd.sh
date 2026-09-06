#!/usr/bin/env bash

set -u

ROOT="/home/biqu/KlipperLCD"
FIRMWARE="$ROOT/firmware/ArtilleryX4KlipperScreen.tft"

STATE_DIR="/home/biqu/.local/state/Artillery-KlipperLCD"
HASH_FILE="$STATE_DIR/tft.sha256"
FAILED_FILE="$STATE_DIR/tft.failed.sha256"

UPLOADER="/home/biqu/.local/bin/nextion-fw-upload"
PORT="/dev/ttyS2"

mkdir -p "$STATE_DIR"

echo "=== Artillery KlipperLCD ==="

if [ -f "$FIRMWARE" ]; then

    NEW_HASH="$(sha256sum "$FIRMWARE" | awk '{print $1}')"
    OLD_HASH="$(cat "$HASH_FILE" 2>/dev/null || true)"
    FAILED_HASH="$(cat "$FAILED_FILE" 2>/dev/null || true)"

    if [ "$NEW_HASH" != "$OLD_HASH" ]; then

        if [ "$NEW_HASH" = "$FAILED_HASH" ]; then
            echo "TFT firmware update for this version previously failed."
            echo "Skipping automatic retry."

        elif [ ! -x "$UPLOADER" ]; then
            echo "ERROR: nextion-fw-upload not found:"
            echo "$UPLOADER"

        else
            echo "New TFT firmware detected."
            echo "Flashing:"
            echo "$FIRMWARE"

            if "$UPLOADER" \
                -b 115200 \
                -ub 115200 \
                -v \
                "$PORT" \
                "$FIRMWARE"
            then
                echo "$NEW_HASH" > "$HASH_FILE"
                rm -f "$FAILED_FILE"

                echo "TFT firmware update successful."
            else
                echo "$NEW_HASH" > "$FAILED_FILE"

                echo "WARNING: TFT firmware update failed."
                echo "KlipperLCD will still be started."
            fi
        fi

    else
        echo "TFT firmware already up to date."
    fi

else
    echo "No TFT firmware found."
fi

echo "Starting KlipperLCD..."

exec /usr/bin/python3 "$ROOT/main.py"
