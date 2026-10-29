import json
import os
import re
import socket
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
EPC_RE = re.compile(r"^(?:[0-9A-F]{2}){1,32}$")
DEVICE_RE = re.compile(r"^playce-[0-9a-f]{6}$")


def load_local_env():
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip("\"'")
        if key and key not in os.environ:
            os.environ[key] = value


load_local_env()
API_BASE = os.getenv("REGISTRATION_API_BASE", "http://playce-admin.mooo.com:4300").rstrip("/")
SITE_ID = os.getenv("REGISTRATION_SITE_ID", "suwon_01")
READER_ID = os.getenv("REGISTRATION_READER_ID", "rp_001")
CLAIM_BASE_URL = os.getenv("REGISTRATION_CLAIM_BASE_URL", "playce://tag-bindings/claim")
TOKEN = os.getenv("REGISTRATION_INTERNAL_API_TOKEN", "").strip()
TOKEN_HEADER = os.getenv("REGISTRATION_INTERNAL_API_TOKEN_HEADER", "Authorization").strip()
TOKEN_SCHEME = os.getenv("REGISTRATION_INTERNAL_API_TOKEN_SCHEME", "Bearer").strip()
HOST = os.getenv("REGISTRATION_UDP_HOST", "0.0.0.0")
PORT = int(os.getenv("REGISTRATION_UDP_PORT", "8767"))
GATEWAY_ID = os.getenv("REGISTRATION_GATEWAY_ID", "").strip().lower()
RESEND_INTERVAL_SECONDS = max(1.0, float(os.getenv("REGISTRATION_RESEND_INTERVAL_SECONDS", "60")))
last_checked = {}


def refresh_api_token():
    """Pick up a token pasted into .env while this listener is already running."""
    env_path = ROOT / ".env"
    if not env_path.exists():
        return TOKEN
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("REGISTRATION_INTERNAL_API_TOKEN="):
            return line.split("=", 1)[1].strip().strip("\"'")
    return TOKEN


def request_json(path, method="GET", payload=None, authenticated=False):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if authenticated and TOKEN:
        headers[TOKEN_HEADER] = f"{TOKEN_SCHEME} {TOKEN}" if TOKEN_SCHEME else TOKEN
    request = Request(API_BASE + path, data=data, headers=headers, method=method)
    with urlopen(request, timeout=8) as response:
        return json.loads(response.read().decode("utf-8"))


def issue_or_reuse(epc, gateway):
    global TOKEN
    TOKEN = refresh_api_token()
    pending = request_json("/v1/registration-challenges/pending").get("challenges", [])
    for challenge in pending:
        if str(challenge.get("epc", "")).upper() == epc:
            print(f"Existing EPC-bound challenge reused: EPC={epc}", flush=True)
            return
    if not TOKEN:
        print("Registration token missing: set REGISTRATION_INTERNAL_API_TOKEN in .env", flush=True)
        return
    payload = {
        "siteId": SITE_ID,
        "readerId": READER_ID,
        "epc": epc,
        "claimBaseUrl": CLAIM_BASE_URL,
    }
    response = request_json("/internal/registration-challenges", "POST", payload, authenticated=True)
    print(f"Challenge created: EPC={epc} challengeId={response.get('challengeId', '?')}", flush=True)


def main():
    print(f"Listening for direct UHF tag events on UDP {HOST}:{PORT}", flush=True)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((HOST, PORT))
        while True:
            raw, address = listener.recvfrom(4096)
            try:
                message = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if message.get("v") != 1 or message.get("event") != "seen":
                continue
            epc = str(message.get("epc", "")).upper()
            device = str(message.get("device", "")).lower()
            gateway = str(message.get("gateway", "")).lower()
            if (not EPC_RE.fullmatch(epc) or message.get("tag_source") != "direct_uhf"
                    or not DEVICE_RE.fullmatch(device) or device != gateway):
                continue
            if GATEWAY_ID and gateway != GATEWAY_ID:
                continue
            now = time.monotonic()
            if now - last_checked.get(epc, 0) < RESEND_INTERVAL_SECONDS:
                continue
            last_checked[epc] = now
            try:
                print(f"Direct tag EPC={epc} receiver={gateway} from={address}", flush=True)
                issue_or_reuse(epc, gateway)
            except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as error:
                print(f"Challenge request failed for EPC={epc}: {error}", flush=True)


if __name__ == "__main__":
    main()
