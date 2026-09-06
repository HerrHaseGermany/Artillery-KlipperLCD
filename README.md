# Artillery-KlipperLCD

Standalone touchscreen service and TFT firmware package for Artillery Sidewinder X4 printers running Klipper.

This project provides everything required to run and update the original Artillery-style touchscreen together with Klipper, Moonraker and Mainsail.

The repository contains:

- the touchscreen service
- the TFT display firmware
- automatic TFT firmware flashing
- a systemd service
- Moonraker / Mainsail Update Manager integration
- an automatic installer

After the initial installation, future updates can be installed directly from the **Mainsail Update Manager**.

---

# Important

This project is currently intended for systems using the same hardware and software layout on which it was developed and tested.

## Tested hardware

- Artillery Sidewinder X4 series
- BIGTREETECH Manta M5P
- BIGTREETECH CB2
- TJC touchscreen compatible with:
  - `TJC4827X243_011C`
- touchscreen connected through:
  - `/dev/ttyS2`
- UART baud rate:
  - `115200`

## Tested software environment

- Linux / Armbian based CB2 system
- Klipper
- Moonraker
- Mainsail
- Python 3.9 or newer
- standard Klipper directory layout:

```text
/home/biqu/printer_data
```

The default installation assumes the Linux user is:

```text
biqu
```

The installer detects the user that executed `sudo`, but the current hardware and directory layout are designed around the standard BTT/CB2 environment.

If your hardware, UART device or installation paths are different, do **not** run the installer without reviewing it first.

---

# What this project does

The touchscreen itself does not communicate directly with Klipper.

The basic architecture is:

```text
Artillery / TJC Touchscreen
          |
          | UART
          | /dev/ttyS2
          |
          v
Artillery-KlipperLCD
          |
          | HTTP / Moonraker API
          |
          v
      Moonraker
          |
          v
       Klipper
```

`KlipperLCD.service` runs the touchscreen application in the background.

The touchscreen service reads touch events from the display and sends commands to Klipper through Moonraker.

It also updates information shown on the touchscreen, such as:

- temperatures
- printer state
- movement controls
- print files
- print status
- bed functions
- macros
- Wi-Fi information
- settings

---

# Features

- Standalone Artillery X4 touchscreen service
- Klipper / Moonraker integration
- bundled TFT touchscreen firmware
- automatic TFT firmware installation
- automatic TFT firmware updates
- SHA-256 firmware version detection
- automatic Nextion/TJC uploader installation
- automatic compatibility fixes for the uploader
- systemd integration
- automatic startup after boot
- Moonraker service authorization
- Mainsail Update Manager support
- automatic service restart after updates
- automatic TFT flashing only when the TFT firmware has actually changed

---

# Installation

## Before you start

The printer should already have working installations of:

- Klipper
- Moonraker
- Mainsail

You should also be able to connect to the printer using SSH.

Example:

```bash
ssh biqu@PRINTER-IP
```

Replace:

```text
PRINTER-IP
```

with the IP address of your printer.

Example:

```bash
ssh biqu@192.168.178.178
```

---

# Step 1 — Connect to the printer

Connect through SSH:

```bash
ssh biqu@PRINTER-IP
```

You should now see a prompt similar to:

```text
biqu@bigtreetech-cb2:~$
```

---

# Step 2 — Download Artillery-KlipperLCD

Go to your home directory:

```bash
cd /home/biqu
```

Clone this repository:

```bash
git clone https://github.com/HerrHaseGermany/Artillery-KlipperLCD.git KlipperLCD
```

Enter the new directory:

```bash
cd /home/biqu/KlipperLCD
```

You can check that the files are present with:

```bash
ls
```

You should see files and directories similar to:

```text
firmware
scripts
src
deploy
docs
install.sh
KlipperLCD.service
main.py
pyproject.toml
LICENSE
NOTICE
README.md
```

---

# Step 3 — Start the installer

Run:

```bash
sudo ./install.sh
```

The installer performs the required setup automatically.

It will:

1. install required Linux packages
2. install required Python packages
3. install the Nextion/TJC firmware uploader
4. replace the problematic `pyserial-asyncio-fast` implementation
5. install `pyserial-asyncio`
6. apply the required uploader compatibility fixes
7. verify `/dev/ttyS2`
8. install `KlipperLCD.service`
9. enable the service at boot
10. authorize the service in Moonraker
11. configure the Moonraker Update Manager
12. start KlipperLCD
13. flash the bundled TFT firmware when required
14. restart Moonraker

The installation may take several minutes.

---

# Step 4 — First TFT firmware installation

On a fresh installation there is no stored touchscreen firmware version.

The first start therefore detects the bundled TFT firmware as new.

The following process happens automatically:

```text
KlipperLCD starts
      |
      v
No installed TFT hash found
      |
      v
New TFT detected
      |
      v
KlipperLCD keeps UART free
      |
      v
TFT firmware is uploaded
      |
      v
Firmware hash is stored
      |
      v
Touchscreen service starts
```

The firmware file is:

```text
firmware/ArtilleryX4KlipperScreen.tft
```

The uploader uses:

```text
/dev/ttyS2
```

at:

```text
115200 baud
```

The equivalent manual uploader command is:

```bash
~/.local/bin/nextion-fw-upload \
  -b 115200 \
  -ub 115200 \
  -v \
  /dev/ttyS2 \
  /home/biqu/KlipperLCD/firmware/ArtilleryX4KlipperScreen.tft
```

## Warning

Do not:

- turn the printer off
- disconnect the display
- reboot the CB2

while TFT firmware is being written.

---

# Step 5 — Check the service

After installation run:

```bash
systemctl status KlipperLCD.service --no-pager -l
```

A healthy service should show:

```text
Active: active (running)
```

The running process should look similar to:

```text
/usr/bin/python3 /home/biqu/KlipperLCD/main.py
```

---

# Step 6 — Check the log

Run:

```bash
journalctl -u KlipperLCD.service -n 50 --no-pager
```

A normal startup should include:

```text
=== Artillery KlipperLCD ===
TFT firmware already up to date.
Starting KlipperLCD...
```

On the first installation you may instead see:

```text
New TFT firmware detected.
Flashing:
...
TFT firmware update successful.
Starting KlipperLCD...
```

---

# Moonraker setup

The installer configures Moonraker automatically.

Normally you do **not** have to edit Moonraker manually.

The following information explains what the installer changes and can also be used for troubleshooting.

---

## Moonraker service permission

Moonraker is not allowed to restart arbitrary Linux services unless they are explicitly authorized.

The installer adds:

```text
KlipperLCD
```

to:

```text
/home/biqu/printer_data/moonraker.asvc
```

You can verify this with:

```bash
grep KlipperLCD /home/biqu/printer_data/moonraker.asvc
```

Expected result:

```text
KlipperLCD
```

If the line is missing, add it manually:

```bash
echo "KlipperLCD" | sudo tee -a /home/biqu/printer_data/moonraker.asvc
```

Then restart Moonraker:

```bash
sudo systemctl restart moonraker
```

---

# Mainsail Update Manager setup

The installer also adds a Moonraker Update Manager section to:

```text
/home/biqu/printer_data/config/moonraker.conf
```

It should contain:

```ini
[update_manager KlipperLCD]
type: git_repo
channel: dev
path: /home/biqu/KlipperLCD
origin: https://github.com/HerrHaseGermany/Artillery-KlipperLCD.git
primary_branch: main
managed_services: KlipperLCD
```

You can check it with:

```bash
grep -A7 '\[update_manager KlipperLCD\]' \
  /home/biqu/printer_data/config/moonraker.conf
```

After changing Moonraker configuration, restart Moonraker:

```bash
sudo systemctl restart moonraker
```

---

# Check Moonraker

Check its status:

```bash
systemctl status moonraker --no-pager -l
```

It should show:

```text
Active: active (running)
```

Check the log if required:

```bash
journalctl -u moonraker -n 50 --no-pager
```

---

# Mainsail

Open Mainsail in your browser.

Go to:

```text
Machine
```

and open the:

```text
Update Manager
```

You should now see an additional component:

```text
KlipperLCD
```

Future updates can be installed from there.

---

# How updates work

When an update is available, Mainsail updates the Git repository.

The process is:

```text
Mainsail Update
      |
      v
Moonraker updates Git repository
      |
      v
KlipperLCD.service restarts
      |
      v
TFT firmware hash is checked
      |
      +------------------+
      |                  |
      v                  v
TFT unchanged        TFT changed
      |                  |
      |                  v
      |              flash display
      |                  |
      +--------+---------+
               |
               v
       start KlipperLCD
```

---

# TFT firmware update detection

The display is **not** flashed during every software update.

Artillery-KlipperLCD calculates a SHA-256 checksum of:

```text
firmware/ArtilleryX4KlipperScreen.tft
```

The checksum of the last successfully installed version is stored outside the Git repository.

Therefore:

## Python code changed

```text
No TFT flash
```

## README changed

```text
No TFT flash
```

## Other service files changed

```text
No TFT flash
```

## TFT firmware changed

```text
Automatic TFT flash
```

After a successful TFT flash, its checksum is stored.

---

# Failed TFT update protection

If a TFT firmware upload fails, the failed firmware hash is recorded.

This prevents the service from repeatedly attempting the same failed flash every few seconds.

The touchscreen service will still attempt to start.

Check the log with:

```bash
journalctl -u KlipperLCD.service -n 100 --no-pager
```

---

# Manual service control

Restart KlipperLCD:

```bash
sudo systemctl restart KlipperLCD.service
```

Stop KlipperLCD:

```bash
sudo systemctl stop KlipperLCD.service
```

Start KlipperLCD:

```bash
sudo systemctl start KlipperLCD.service
```

Check status:

```bash
systemctl status KlipperLCD.service --no-pager -l
```

Follow the live log:

```bash
journalctl -fu KlipperLCD.service
```

Press:

```text
Ctrl+C
```

to stop following the log.

---

# Manual TFT firmware flash

Normally this is **not necessary**.

The automatic updater should handle TFT firmware changes.

If a manual flash is required, first stop KlipperLCD because both the service and the uploader use `/dev/ttyS2`.

Stop the service:

```bash
sudo systemctl stop KlipperLCD.service
```

Verify that it is stopped:

```bash
systemctl is-active KlipperLCD.service
```

Expected result:

```text
inactive
```

Check whether another program is using the UART:

```bash
sudo fuser /dev/ttyS2
```

Ideally this produces no output.

Now flash:

```bash
~/.local/bin/nextion-fw-upload \
  -b 115200 \
  -ub 115200 \
  -v \
  /dev/ttyS2 \
  /home/biqu/KlipperLCD/firmware/ArtilleryX4KlipperScreen.tft
```

A successful upload should end with a message similar to:

```text
Successfully uploaded ... bytes
```

Start KlipperLCD again:

```bash
sudo systemctl start KlipperLCD.service
```

---

# Troubleshooting

## KlipperLCD does not start

Check:

```bash
systemctl status KlipperLCD.service --no-pager -l
```

Then:

```bash
journalctl -u KlipperLCD.service -n 100 --no-pager
```

---

## `/dev/ttyS2` does not exist

Check available serial devices:

```bash
ls -l /dev/ttyS*
```

The current installation expects:

```text
/dev/ttyS2
```

If your touchscreen uses a different UART, the installer and startup script must be adapted.

---

## Permission denied on `/dev/ttyS2`

Check the user's groups:

```bash
groups biqu
```

The service uses:

```ini
SupplementaryGroups=dialout
```

Check the UART permissions:

```bash
ls -l /dev/ttyS2
```

---

## Moonraker warning

If Moonraker reports:

```text
Moonraker is not permitted to restart service 'KlipperLCD'
```

check:

```bash
cat /home/biqu/printer_data/moonraker.asvc
```

It must contain:

```text
KlipperLCD
```

If not:

```bash
echo "KlipperLCD" | sudo tee -a \
  /home/biqu/printer_data/moonraker.asvc
```

Then:

```bash
sudo systemctl restart moonraker
```

---

## KlipperLCD does not appear in Mainsail Update Manager

Check:

```bash
grep -A7 '\[update_manager KlipperLCD\]' \
  /home/biqu/printer_data/config/moonraker.conf
```

Then restart Moonraker:

```bash
sudo systemctl restart moonraker
```

Check its log:

```bash
journalctl -u moonraker -n 100 --no-pager
```

---

## Moonraker is unavailable

If the KlipperLCD log contains:

```text
Moonraker is unavailable
```

check Moonraker:

```bash
systemctl status moonraker --no-pager -l
```

Restart it if necessary:

```bash
sudo systemctl restart moonraker
```

---

## Klippy Host not connected

If the log contains:

```text
Klippy Host not connected
```

check Klipper:

```bash
systemctl status klipper --no-pager -l
```

Check the Klipper log or Mainsail for configuration errors.

---

## Screen stays black

First check whether the service is running:

```bash
systemctl status KlipperLCD.service --no-pager -l
```

Then inspect:

```bash
journalctl -u KlipperLCD.service -n 100 --no-pager
```

If necessary restart:

```bash
sudo systemctl restart KlipperLCD.service
```

---

# Repository structure

```text
Artillery-KlipperLCD/
├── deploy/
├── docs/
├── firmware/
│   └── ArtilleryX4KlipperScreen.tft
├── scripts/
│   └── start-klipperlcd.sh
├── src/
│   └── artillery_screen/
│       ├── app.py
│       ├── i18n.py
│       ├── models.py
│       ├── moonraker.py
│       ├── network.py
│       ├── nextion.py
│       ├── protocol.py
│       ├── settings.py
│       ├── storage.py
│       └── ui_labels.py
├── install.sh
├── KlipperLCD.service
├── main.py
├── pyproject.toml
├── LICENSE
├── NOTICE
└── README.md
```

---

# Python dependencies

The application requires Python 3.9 or newer.

Application dependencies are defined in:

```text
pyproject.toml
```

Currently:

```text
pyserial >= 3.5
requests >= 2.25
```

The installer additionally installs the packages required for TFT firmware uploading.

---

# Development

Do not permanently edit files directly on an installed printer unless you intend to commit those changes.

Moonraker expects the Git repository to remain clean for reliable updates.

Check the repository:

```bash
cd /home/biqu/KlipperLCD
git status
```

A normal installed system should show:

```text
nothing to commit, working tree clean
```

---

# Creating changes

After modifying the source:

```bash
cd /home/biqu/KlipperLCD
git status
git add .
git commit -m "Describe the change"
git push
```

---

# Releases

Semantic version tags are recommended.

Example:

```bash
git tag v0.2.1
git push origin v0.2.1
```

---

# Project history

Artillery-KlipperLCD was **not created from scratch**.

It continues and adapts existing community work around factory touchscreens and Klipper.

The development lineage is approximately:

```text
joakimtoe/KlipperLCD
        |
        v
Tortillery Artillery X4 adaptation
        |
        v
ArtilleryX4PlusScreenService
        |
        v
Artillery-KlipperLCD
```

---

# Acknowledgements

Special thanks and attribution go to the following projects and contributors.

## joakimtoe/KlipperLCD

https://github.com/joakimtoe/KlipperLCD

The original KlipperLCD project for the Elegoo Neptune 3 Pro display.

It represents the primary upstream origin of the KlipperLCD touchscreen service concept and code lineage used by this project.

KlipperLCD is licensed under the Apache License 2.0.

---

## Tortillery

https://github.com/CiareCw455/Tortillery

Tortillery adapted KlipperLCD and touchscreen firmware for the Artillery Sidewinder X4 Pro / X4 Plus family.

Tortillery explicitly credits Joakimtoe and the original KlipperLCD project for its touchscreen work.

Many Artillery-specific concepts and adaptations in this project originate from or were inspired by that community work.

---

## ArtilleryX4PlusScreenService

https://github.com/mechano/ArtilleryX4PlusScreenService

This project provided a standalone distribution of the Artillery X4 KlipperLCD service derived from the Tortillery firmware project.

It helped establish the standalone Artillery X4 service lineage continued here.

---

## Tortillery community

Thanks also to the contributors and Artillery X4 community members involved in:

- testing
- touchscreen adaptation
- firmware development
- Artillery X4 configuration
- Klipper integration

Their work made the later development of this standalone package possible.

---

# What Artillery-KlipperLCD adds

This repository further develops that upstream work by providing:

- one standalone Git repository
- integrated touchscreen application source
- integrated TFT firmware
- automatic TFT installation
- TFT SHA-256 version tracking
- automatic firmware updates
- automatic Nextion uploader setup
- systemd installation
- Moonraker authorization
- Mainsail Update Manager integration
- reproducible installation for compatible CB2 systems
- additional user interface and protocol development

---

# License

This repository is distributed under the:

**Apache License 2.0**

See:

```text
LICENSE
```

for the complete license text.

The original:

```text
joakimtoe/KlipperLCD
```

project is also distributed under Apache-2.0.

The Tortillery documentation identifies its KlipperLCD component as Apache-2.0.

Tortillery as a complete firmware distribution uses GPL-3.0 because the complete project combines components distributed under different licenses.

Artillery-KlipperLCD is intended as a continuation and adaptation of the KlipperLCD / touchscreen service lineage and **not** as a redistribution or relicensing of the complete Tortillery firmware distribution.

Original copyright, license and attribution notices remain the property of their respective authors and contributors.

See also:

```text
NOTICE
```

for project attribution information.

---

# TFT firmware attribution

The bundled TFT firmware and Artillery-specific touchscreen adaptations may include or build upon community-derived work from the upstream projects acknowledged above.

Any additional upstream authorship or licensing information discovered in the future should be retained and added to this repository.

---

# Trademarks

Artillery, BIGTREETECH, Elegoo, Klipper, Moonraker, Mainsail, Nextion and TJC are names and/or trademarks belonging to their respective owners.

Their use here is solely for identification and compatibility information.

---

# Disclaimer

This is an independent community project.

It is not affiliated with or endorsed by:

- Artillery
- BIGTREETECH
- Elegoo
- Klipper
- Moonraker
- Mainsail
- Nextion
- TJC
- the upstream projects mentioned above

Use this software and firmware at your own risk.

Flashing touchscreen firmware always carries some risk.

Verify that your hardware matches the supported configuration before installation.

---

# Quick installation summary

For a compatible printer with Klipper, Moonraker and Mainsail already installed:

```bash
ssh biqu@PRINTER-IP
```

then:

```bash
cd /home/biqu

git clone \
https://github.com/HerrHaseGermany/Artillery-KlipperLCD.git \
KlipperLCD

cd KlipperLCD

sudo ./install.sh
```

Then check:

```bash
systemctl status KlipperLCD.service --no-pager -l
```

and:

```bash
journalctl -u KlipperLCD.service -n 50 --no-pager
```

Finally open Mainsail and verify that:

```text
KlipperLCD
```

appears in the Update Manager.
