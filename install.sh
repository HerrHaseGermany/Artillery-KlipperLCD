#!/usr/bin/env bash
set -euo pipefail

echo
echo "========================================"
echo " Artillery KlipperLCD Installer"
echo "========================================"
echo

if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: Please run with sudo:"
    echo "sudo ./install.sh"
    exit 1
fi

USER_NAME="${SUDO_USER:-biqu}"

if ! id "$USER_NAME" >/dev/null 2>&1; then
    echo "ERROR: User '$USER_NAME' does not exist."
    exit 1
fi

USER_HOME="$(getent passwd "$USER_NAME" | cut -d: -f6)"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

MOONRAKER_DATA="$USER_HOME/printer_data"
MOONRAKER_CONF="$MOONRAKER_DATA/config/moonraker.conf"
MOONRAKER_ASVC="$MOONRAKER_DATA/moonraker.asvc"

SERVICE_NAME="KlipperLCD"
PORT="/dev/ttyS2"

echo "User:       $USER_NAME"
echo "Home:       $USER_HOME"
echo "Repository: $REPO_DIR"
echo "UART:       $PORT"
echo

echo "[1/8] Installing system packages..."

apt-get update
apt-get install -y \
    python3 \
    python3-pip \
    git

echo
echo "[2/8] Installing Python dependencies..."

sudo -u "$USER_NAME" -H python3 -m pip install --user \
    "pyserial>=3.5" \
    "requests>=2.25" \
    nextion \
    pyserial-asyncio

echo
echo "[3/8] Applying Nextion uploader compatibility fixes..."

NEXTION_CLIENT="$(
    sudo -u "$USER_NAME" -H python3 - <<'PY'
import nextion.client
print(nextion.client.__file__)
PY
)"

echo "Nextion client: $NEXTION_CLIENT"

sudo -u "$USER_NAME" -H python3 - "$NEXTION_CLIENT" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text()

text = text.replace(
    "import serial_asyncio_fast as serial_asyncio",
    "import serial_asyncio"
)

text = text.replace(
    'logger.info(f"Reconnecting at new baud rate: {upload_baud}" % (upload_baud))',
    'logger.info(f"Reconnecting at new baud rate: {upload_baud}")'
)

path.write_text(text)
PY

sudo -u "$USER_NAME" -H python3 -m pip uninstall -y \
    pyserial-asyncio-fast || true

sudo -u "$USER_NAME" -H python3 -m pip install --user \
    pyserial-asyncio

sudo -u "$USER_NAME" -H python3 -m py_compile "$NEXTION_CLIENT"

UPLOADER="$USER_HOME/.local/bin/nextion-fw-upload"

if [ ! -x "$UPLOADER" ]; then
    echo "ERROR: nextion-fw-upload was not installed correctly."
    exit 1
fi

echo "Nextion uploader OK: $UPLOADER"

echo
echo "[4/8] Checking UART..."

if [ ! -e "$PORT" ]; then
    echo "ERROR: $PORT does not exist."
    exit 1
fi

echo "$PORT found."

echo
echo "[5/8] Installing KlipperLCD service..."

chmod +x "$REPO_DIR/scripts/start-klipperlcd.sh"

cat > /etc/systemd/system/KlipperLCD.service <<SERVICE
[Unit]
Description=KlipperLCD Service
After=klipper.service moonraker.service

[Service]
Type=simple
User=$USER_NAME
SupplementaryGroups=dialout
WorkingDirectory=$REPO_DIR
Environment=PYTHONUNBUFFERED=1
ExecStart=$REPO_DIR/scripts/start-klipperlcd.sh
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
SERVICE

systemctl daemon-reload
systemctl enable KlipperLCD.service

echo
echo "[6/8] Configuring Moonraker service permission..."

if [ -f "$MOONRAKER_ASVC" ]; then
    grep -qxF "$SERVICE_NAME" "$MOONRAKER_ASVC" || \
        echo "$SERVICE_NAME" >> "$MOONRAKER_ASVC"
else
    echo "WARNING: $MOONRAKER_ASVC not found."
fi

echo
echo "[7/8] Configuring Moonraker Update Manager..."

if [ -d "$REPO_DIR/.git" ]; then
    ORIGIN="$(sudo -u "$USER_NAME" git -C "$REPO_DIR" remote get-url origin)"
else
    ORIGIN="https://github.com/HerrHaseGermany/Artillery-KlipperLCD.git"
fi

if [ -f "$MOONRAKER_CONF" ]; then

    if ! grep -q '^\[update_manager KlipperLCD\]' "$MOONRAKER_CONF"; then

        cat >> "$MOONRAKER_CONF" <<MOONRAKER

[update_manager KlipperLCD]
type: git_repo
channel: dev
path: $REPO_DIR
origin: $ORIGIN
primary_branch: main
managed_services: KlipperLCD
MOONRAKER

        echo "Moonraker Update Manager entry added."
    else
        echo "Moonraker Update Manager already configured."
    fi

else
    echo "WARNING: moonraker.conf not found:"
    echo "$MOONRAKER_CONF"
fi

echo
echo "[8/8] Starting services..."

systemctl restart KlipperLCD.service

if systemctl is-active --quiet moonraker.service; then
    systemctl restart moonraker.service
fi

echo
echo "========================================"
echo " Installation complete"
echo "========================================"
echo
echo "KlipperLCD:"
systemctl --no-pager --full status KlipperLCD.service | head -n 10 || true
echo
echo "Firmware will automatically be flashed"
echo "on first start if required."
echo
