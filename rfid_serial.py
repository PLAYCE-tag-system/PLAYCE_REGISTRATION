import json
import re
import time

import serial
from serial.tools import list_ports


INVENTORY_COMMAND = bytes.fromhex("BB0027000322FFFF4A7E")
TAG_DETECTED_RE = re.compile(r"(?i)^TAG_DETECTED\s*,\s*([0-9a-f][0-9a-f\s:-]*[0-9a-f])(?:\s*,.*)?$")
LABELLED_EPC_RE = re.compile(
    r"(?i)(?:\"?epc\"?(?:\s+detected)?|\"?tag\"?)\s*[:=]\s*\"?([0-9a-f][0-9a-f\s:-]*[0-9a-f])"
)

GATEWAY_STATUS_LINES = (
    "RFID Reader Ready",
    "RFID command loop mode enabled",
    "RFID command sent",
    "RFID_WAITING_FOR_TAG",
    "TAG_LOST",
    "No tag detected",
    "Invalid frame length",
    "Checksum error",
)


class RegistrationSerialReader:
    def __init__(
        self,
        port,
        baudrate=115200,
        source_mode="esp32",
        resend_interval_seconds=60.0,
        startup_wait_seconds=2.0,
        command_retry_seconds=3.0,
        no_serial_warn_seconds=10.0,
        no_tag_warn_seconds=15.0,
        debug=False,
    ):
        self.port = port
        self.baudrate = baudrate
        self.source_mode = normalize_source_mode(source_mode)
        self.resend_interval_seconds = resend_interval_seconds
        self.startup_wait_seconds = startup_wait_seconds
        self.command_retry_seconds = command_retry_seconds
        self.no_serial_warn_seconds = no_serial_warn_seconds
        self.no_tag_warn_seconds = no_tag_warn_seconds
        self.debug = debug
        self.ser = serial.Serial(port, baudrate, timeout=1)
        self.tag_data = {}
        self.tag_index = 0
        now_ts = time.time()
        self.last_serial_time = now_ts
        self.last_tag_time = now_ts
        self.last_command_time = 0
        self.no_serial_message_shown = False
        self.no_tag_message_shown = False
        self.has_received_serial = False
        self.wait_for_startup()

    def wait_for_startup(self):
        if self.startup_wait_seconds <= 0:
            return

        deadline = time.time() + self.startup_wait_seconds
        while time.time() < deadline:
            if self.ser.in_waiting > 0:
                self.process_serial_response(self.ser.read(self.ser.in_waiting), source="STARTUP")
            time.sleep(0.1)

    def read_forever(self):
        if self.uses_direct_inventory():
            self.send_inventory_command("startup")
        else:
            print("ESP32 gateway mode: inventory command is not sent from Python.")

        try:
            while True:
                if self.ser.in_waiting > 0:
                    self.process_serial_response(self.ser.read(self.ser.in_waiting))

                if self.should_retry_inventory():
                    self.send_inventory_command("retry")

                if self.should_warn_no_serial():
                    print("Serial data is not arriving. Check port, firmware upload, USB cable, and baudrate.")
                    self.no_serial_message_shown = True

                if self.should_warn_no_tag():
                    print("Reader is connected, but no tag EPC has been received yet.")
                    self.no_tag_message_shown = True

                time.sleep(0.1)
        finally:
            self.close()

    def uses_direct_inventory(self):
        return self.source_mode == "direct"

    def send_inventory_command(self, reason):
        written = self.ser.write(INVENTORY_COMMAND)
        self.last_command_time = time.time()
        if self.debug:
            print(f"[SERIAL CMD] {INVENTORY_COMMAND.hex().upper()} ({written} bytes, reason={reason})")

    def should_retry_inventory(self):
        if not self.uses_direct_inventory():
            return False
        if self.command_retry_seconds <= 0 or self.last_command_time <= 0:
            return False
        now_ts = time.time()
        return (
            now_ts - self.last_serial_time >= self.command_retry_seconds
            and now_ts - self.last_command_time >= self.command_retry_seconds
        )

    def should_warn_no_serial(self):
        return (
            not self.no_serial_message_shown
            and self.no_serial_warn_seconds > 0
            and time.time() - self.last_serial_time > self.no_serial_warn_seconds
        )

    def should_warn_no_tag(self):
        return (
            not self.no_tag_message_shown
            and self.has_received_serial
            and self.no_tag_warn_seconds > 0
            and time.time() - self.last_tag_time > self.no_tag_warn_seconds
        )

    def process_serial_response(self, response, source="SERIAL"):
        hex_response = response.hex().upper()
        text_response = response.decode("utf-8", errors="ignore")
        self.last_serial_time = time.time()
        self.has_received_serial = True
        self.no_serial_message_shown = False

        if self.debug:
            print(f"[{source} HEX] {hex_response}")
            if any(not character.isspace() for character in text_response):
                print(f"[{source} TEXT] {text_response.strip()}")

        epcs = extract_epcs(hex_response, text_response)
        if not epcs and is_gateway_status_text(text_response):
            return

        if not epcs and self.debug:
            print("EPC was not found in this serial frame.")

        for epc in epcs:
            self.handle_tag(epc)

    def handle_tag(self, epc):
        normalized_epc = normalize_epc(epc)
        display_epc = format_epc(normalized_epc)
        now_ts = time.time()
        self.last_tag_time = now_ts
        self.no_tag_message_shown = False

        if normalized_epc not in self.tag_data:
            self.tag_index += 1
            self.tag_data[normalized_epc] = {
                "index": self.tag_index,
                "last_sent": now_ts,
                "count": 1,
            }
            print(f"[{self.tag_index}] EPC: {display_epc}, first seen")
            self.on_tag(normalized_epc)
            return

        self.tag_data[normalized_epc]["count"] += 1
        last_sent = self.tag_data[normalized_epc].get("last_sent", 0)
        if now_ts - last_sent > self.resend_interval_seconds:
            self.tag_data[normalized_epc]["last_sent"] = now_ts
            print(f"[{self.tag_data[normalized_epc]['index']}] EPC: {display_epc}, seen again")
            self.on_tag(normalized_epc)
            return

        count = self.tag_data[normalized_epc]["count"]
        index = self.tag_data[normalized_epc]["index"]
        print(f"[{index}] EPC: {display_epc}, count: {count}")

    def on_tag(self, epc):
        raise NotImplementedError("Registration reader must implement on_tag")

    def close(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
            print("Serial port closed.")


def extract_epcs(hex_response, text_response=""):
    normalized_response = normalize_hex(hex_response)
    epc_values = []

    for payload in iter_frame_payloads(normalized_response):
        append_epc(epc_values, extract_epc_from_payload(payload))

    scan_raw_pc_words = not epc_values
    for epc_hex in extract_epcs_from_raw_response(normalized_response, scan_raw_pc_words):
        append_epc(epc_values, epc_hex)

    for epc_hex in extract_epcs_from_text(text_response):
        append_epc(epc_values, epc_hex)

    return epc_values


def extract_epcs_from_text(text_response):
    epc_values = []
    for line in str(text_response).splitlines():
        append_epc(epc_values, extract_epc_from_json_line(line))

        match = TAG_DETECTED_RE.search(line)
        if match:
            append_epc(epc_values, normalize_epc(match.group(1)))
            continue

        match = LABELLED_EPC_RE.search(line)
        if match:
            append_epc(epc_values, normalize_epc(match.group(1)))
            continue

        for bare_epc in extract_epcs_from_hex_text_line(line):
            append_epc(epc_values, bare_epc)
    return epc_values


def extract_epc_from_json_line(line):
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return None

    if not isinstance(payload, dict):
        return None

    for key in ("epc", "tag"):
        value = payload.get(key)
        if isinstance(value, str) and is_valid_epc_hex(normalize_epc(value)):
            return normalize_epc(value)
    return None


def extract_epcs_from_hex_text_line(line):
    raw_line = str(line).strip()
    if not re.fullmatch(r"[0-9A-Fa-f\s:-]+", raw_line):
        return []

    hex_text = normalize_epc(raw_line)
    if not is_valid_epc_hex(hex_text):
        return []

    epc_values = []
    if hex_text.startswith("BB"):
        for payload in iter_frame_payloads(hex_text):
            append_epc(epc_values, extract_epc_from_payload(payload))

        scan_raw_pc_words = not epc_values
        for epc_hex in extract_epcs_from_raw_response(hex_text, scan_raw_pc_words):
            append_epc(epc_values, epc_hex)
        return epc_values

    if len(hex_text) >= 8:
        append_epc(epc_values, hex_text)
    return epc_values


def extract_epcs_from_raw_response(hex_response, scan_pc_words):
    epc_values = []
    for legacy_epc in extract_fixed_length_epcs_after_prefix(hex_response, "E280", 24):
        append_epc(epc_values, legacy_epc)

    if epc_values or not scan_pc_words:
        return epc_values

    for frame_start in iter_frame_starts(hex_response):
        if hex_response[frame_start : frame_start + 6] != "BB0222":
            continue

        search_start = frame_start + 10
        search_end = raw_frame_search_end(hex_response, frame_start)
        for epc_hex in extract_epcs_by_scanning_pc_words(hex_response[search_start:search_end]):
            append_epc(epc_values, epc_hex)
    return epc_values


def extract_fixed_length_epcs_after_prefix(hex_response, prefix, length):
    epc_values = []
    cursor = 0
    while cursor < len(hex_response):
        epc_start = hex_response.find(prefix, cursor)
        if epc_start == -1:
            return epc_values

        append_epc(epc_values, hex_response[epc_start : epc_start + length])
        cursor = epc_start + max(len(prefix), 2)
    return epc_values


def iter_frame_payloads(hex_response):
    cursor = 0
    while cursor + 10 <= len(hex_response):
        frame_start = hex_response.find("BB", cursor)
        if frame_start == -1 or frame_start + 10 > len(hex_response):
            return

        try:
            payload_length = int(hex_response[frame_start + 6 : frame_start + 10], 16)
        except ValueError:
            cursor = frame_start + 2
            continue

        payload_start = frame_start + 10
        payload_end = payload_start + payload_length * 2
        frame_end = payload_end + 4
        if frame_end <= len(hex_response) and hex_response[frame_end - 2 : frame_end] == "7E":
            payload = hex_response[payload_start:payload_end]
            if is_valid_epc_hex(payload):
                yield payload
            cursor = frame_end
            continue

        cursor = frame_start + 2


def extract_epc_from_payload(payload):
    for pc_offset in (2, 0):
        epc_hex = extract_epc_after_pc(payload, pc_offset)
        if epc_hex:
            return epc_hex

    for epc_start in (6, 4):
        epc_hex = payload[epc_start:-4]
        if is_valid_epc_hex(epc_hex):
            return epc_hex
    return None


def extract_epc_after_pc(payload, pc_offset):
    pc_start = pc_offset
    pc_end = pc_start + 4
    if len(payload) < pc_end + 6:
        return None

    try:
        pc_word = int(payload[pc_start:pc_end], 16)
    except ValueError:
        return None

    epc_words = (pc_word >> 11) & 0x1F
    if epc_words <= 0:
        return None

    epc_start = pc_end
    epc_end = epc_start + epc_words * 4
    if len(payload) < epc_end + 4:
        return None

    epc_hex = payload[epc_start:epc_end]
    if is_valid_epc_hex(epc_hex):
        return epc_hex
    return None


def extract_epcs_by_scanning_pc_words(hex_response):
    epc_values = []
    for pc_start in range(0, max(len(hex_response) - 4, 0), 2):
        append_epc(epc_values, extract_epc_after_pc(hex_response[pc_start:], 0))
    return epc_values


def iter_frame_starts(hex_response):
    cursor = 0
    while cursor < len(hex_response):
        frame_start = hex_response.find("BB", cursor)
        if frame_start == -1:
            return
        yield frame_start
        cursor = frame_start + 2


def raw_frame_search_end(hex_response, frame_start):
    if frame_start + 10 > len(hex_response):
        return len(hex_response)

    try:
        payload_length = int(hex_response[frame_start + 6 : frame_start + 10], 16)
    except ValueError:
        return len(hex_response)

    payload_end = frame_start + 10 + payload_length * 2
    return min(len(hex_response), payload_end + 4)


def append_epc(epc_values, epc_hex):
    if not epc_hex:
        return
    normalized_epc = normalize_epc(epc_hex)
    if is_valid_epc_hex(normalized_epc) and normalized_epc not in epc_values:
        epc_values.append(normalized_epc)


def normalize_epc(value):
    return re.sub(r"[^0-9A-Fa-f]", "", str(value)).upper()


def normalize_hex(value):
    return "".join(str(value).split()).upper()


def is_valid_epc_hex(epc_hex):
    return (
        len(epc_hex) >= 2
        and len(epc_hex) % 2 == 0
        and all(character in "0123456789ABCDEF" for character in epc_hex)
    )


def format_epc(epc_hex):
    normalized_epc = normalize_epc(epc_hex)
    return " ".join(normalized_epc[i : i + 2] for i in range(0, len(normalized_epc), 2))


def is_gateway_status_text(text_response):
    text = str(text_response).strip()
    if not text:
        return False
    return any(line in text for line in GATEWAY_STATUS_LINES)


def normalize_source_mode(source_mode):
    value = str(source_mode or "esp32").strip().lower()
    if value in {"esp32", "gateway", "cluster"}:
        return "esp32"
    if value == "direct":
        return "direct"
    print(f"Unknown REGISTRATION_SOURCE_MODE={source_mode}; using esp32.")
    return "esp32"


def normalize_port(port):
    value = str(port).strip().lstrip("\ufeff")
    if value.isdigit():
        return f"COM{value}"
    return value


def print_available_ports():
    ports = list(list_ports.comports())
    if not ports:
        print("No serial ports were detected.")
        return

    print("Detected serial ports:")
    for item in ports:
        print(f"  - {format_port_info(item)}")


def format_port_info(port_info):
    parts = [f"{port_info.device}: {port_info.description}"]
    for attr_name in ("hwid", "manufacturer", "product", "serial_number"):
        attr_value = getattr(port_info, attr_name, None)
        if attr_value:
            parts.append(f"{attr_name}={attr_value}")
    return " | ".join(parts)
