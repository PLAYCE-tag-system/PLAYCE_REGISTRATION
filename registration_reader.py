import os
import time

import serial
from dotenv import load_dotenv

from http_client import delete_json, get_json, post_json
from rfid_serial import RegistrationSerialReader, normalize_port, print_available_ports


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

REGISTRATION_API_BASE = os.getenv("REGISTRATION_API_BASE", "http://127.0.0.1:4300").rstrip("/")
REGISTRATION_SITE_ID = os.getenv("REGISTRATION_SITE_ID", "suwon_01")
REGISTRATION_READER_ID = os.getenv("REGISTRATION_READER_ID", "rp_001")
REGISTRATION_CLAIM_BASE_URL = os.getenv(
    "REGISTRATION_CLAIM_BASE_URL",
    "khuround://tag-bindings/claim",
)


class RegistrationReader(RegistrationSerialReader):
    def on_tag(self, epc):
        create_registration_challenge(epc)


def create_registration_challenge(epc):
    challenge_data = {
        "siteId": REGISTRATION_SITE_ID,
        "readerId": REGISTRATION_READER_ID,
        "epc": epc,
        "claimBaseUrl": REGISTRATION_CLAIM_BASE_URL,
    }

    max_retries = 3
    for attempt in range(max_retries):
        try:
            print(f"Sending registration QR challenge... EPC={epc}")
            payload = post_json(
                REGISTRATION_API_BASE,
                "/internal/registration-challenges",
                challenge_data,
            )
            print(f"QR challenge created: {payload['challengeId']}")
            return
        except Exception as error:
            print(f"Challenge request failed ({attempt + 1}/{max_retries}): {error}")
            if attempt < max_retries - 1:
                time.sleep(2)
            else:
                print(f"Final challenge request failed. EPC={epc}")


def clear_current_scan_collection():
    try:
        print("Clearing pending registration challenges...")
        pending = get_json(REGISTRATION_API_BASE, "/v1/registration-challenges/pending").get(
            "challenges",
            [],
        )
        for challenge in pending:
            delete_json(
                REGISTRATION_API_BASE,
                f"/internal/registration-challenges/{challenge['challengeId']}",
            )
        print(f"Pending challenge cleanup complete: {len(pending)} removed.")
    except Exception as error:
        print(f"Pending challenge cleanup failed: {error}")


def main():
    print(f"Registration backend: {REGISTRATION_API_BASE}")
    print(f"Registration reader: site={REGISTRATION_SITE_ID}, reader={REGISTRATION_READER_ID}")

    if read_bool_env("REGISTRATION_CLEAR_PENDING_ON_START", True):
        clear_current_scan_collection()

    port = os.getenv("REGISTRATION_SERIAL_PORT")
    if not port:
        print_available_ports()
        port = input("Registration reader serial port (example: /dev/ttyUSB0, COM8, or 8): ")
    port = normalize_port(port)

    source_mode = os.getenv("REGISTRATION_SOURCE_MODE", "esp32")
    print(f"Selected port: {port}")
    print(f"Source mode: {source_mode}")

    try:
        reader = RegistrationReader(
            port=port,
            baudrate=read_int_env("REGISTRATION_BAUDRATE", 115200),
            source_mode=source_mode,
            resend_interval_seconds=read_float_env("REGISTRATION_RESEND_INTERVAL_SECONDS", 60.0),
            startup_wait_seconds=read_float_env("REGISTRATION_STARTUP_WAIT_SECONDS", 2.0),
            command_retry_seconds=read_float_env("REGISTRATION_COMMAND_RETRY_SECONDS", 3.0),
            debug=read_bool_env("REGISTRATION_DEBUG", False),
        )
    except serial.SerialException as error:
        print(f"Could not open serial port: {error}")
        return

    try:
        reader.read_forever()
    except serial.SerialException as error:
        print(f"Serial error: {error}")
    except KeyboardInterrupt:
        print("Stopped by user.")
    finally:
        reader.close()


def read_int_env(name, default):
    value = os.getenv(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        print(f"{name} is not an integer. Using {default}.")
        return default


def read_float_env(name, default):
    value = os.getenv(name)
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        print(f"{name} is not a number. Using {default}.")
        return default


def read_bool_env(name, default):
    value = os.getenv(name)
    if not value:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


if __name__ == "__main__":
    main()
