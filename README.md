# PLAYCE Registration

Registration-device code for Linux/Raspberry Pi.

This repository contains only the field registration station:

- Python registration reader service
- QR display web app
- ESP32 UHF reader sketch

The backend, admin page, Android app, and detection readers are separate deployments.

## Flow

```text
ESP32/UHF registration reader
  -> registration_reader.py
  -> Backend POST /internal/registration-challenges
  -> qr-display/qr.html polls /v1/registration-challenges/current
  -> PLAYCE app scans the QR from the profile/tag registration screen
```

`registration_reader.py` creates QR registration challenges only. It does not post detection scan events.

## Raspberry Pi Setup

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip nodejs npm

python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
```

Edit `.env` for the backend host and serial port.

## Python Registration Reader

ESP32 gateway mode is the default. In this mode the ESP32 sends text lines such as:

```text
TAG_DETECTED,E280F30200000000DE25E8CA,201
```

Run:

```bash
python registration_reader.py
```

For a direct UHF serial reader that expects the PC/Pi to send the inventory command, set:

```bash
REGISTRATION_SOURCE_MODE=direct
```

## QR Display

```bash
cd qr-display
npm ci
npm run dev -- --host 0.0.0.0
```

Open:

```text
http://<raspberry-pi-ip>:5173/qr.html
```

## ESP32 Firmware

Upload `firmware/esp32_uhf_registration_reader/esp32_uhf_registration_reader.ino` with Arduino IDE.

Expected serial output:

```text
RFID Reader Ready (ESP32).
RFID command loop mode enabled.
TAG_DETECTED,E280F30200000000DE25E8CA,201
```

## Environment

See `.env.example`.

Registration reader IDs use the `rp_*` prefix. The default is `rp_001`.
