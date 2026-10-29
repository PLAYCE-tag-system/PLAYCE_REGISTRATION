import json
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen

import qrcode
from qrcode.image.svg import SvgPathImage


ROOT = Path(__file__).resolve().parent
FONT_TYPES = {
    "/fonts/Freesentation-9Black.woff2": "font/woff2",
    "/fonts/Paperlogy-5Medium.woff2": "font/woff2",
    "/fonts/RIDIBatang.woff": "font/woff",
}
COLLECTOR_BASE = os.getenv("QR_COLLECTOR_BASE", "http://127.0.0.1:8765").rstrip("/")
REGISTRATION_API_BASE = os.getenv(
    "REGISTRATION_API_BASE", "http://playce-admin.mooo.com:4300"
).rstrip("/")
HOST = os.getenv("QR_HOST", "0.0.0.0")
PORT = int(os.getenv("QR_PORT", "5173"))
EPC_LENGTH_LIMIT = 64
DIRECT_RECEIVER_ID = os.getenv("QR_DIRECT_RECEIVER_ID", "playce-ca9bd0").strip().lower()


def fetch_json(url):
    request = Request(url, headers={"Accept": "application/json", "Cache-Control": "no-cache"})
    with urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlsplit(self.path)
        if parsed.path in {"/", "/qr.html"}:
            body = (ROOT / "qr.html").read_bytes()
            self.respond(200, "text/html; charset=utf-8", body)
            return
        if parsed.path in FONT_TYPES:
            body = (ROOT / "fonts" / parsed.path.removeprefix("/fonts/")).read_bytes()
            self.respond(200, FONT_TYPES[parsed.path], body)
            return
        if parsed.path == "/api/direct-tags":
            self.direct_tags()
            return
        if parsed.path == "/api/challenge":
            self.challenge(parse_qs(parsed.query).get("epc", [""])[0])
            return
        if parsed.path == "/api/qr.svg":
            self.qr(parse_qs(parsed.query).get("value", [""])[0])
            return
        self.respond(404, "application/json; charset=utf-8", b'{"error":"not found"}')

    def direct_tags(self):
        try:
            state = fetch_json(f"{COLLECTOR_BASE}/api/state")
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
            self.respond_json(503, {"error": f"collector unavailable: {error}"})
            return
        tags = []
        for device in state.get("devices", []):
            if (device.get("role") != "gateway"
                    or str(device.get("device", "")).lower() != DIRECT_RECEIVER_ID):
                continue
            for tag in device.get("tags", []):
                if (tag.get("active") and tag.get("tag_source") == "direct_uhf"
                        and not tag.get("relay_path")):
                    tags.append({
                        "epc": str(tag.get("epc", "")).upper(),
                        "last_seen": float(tag.get("last_seen", 0)),
                    })
        tags.sort(key=lambda tag: tag["last_seen"], reverse=True)
        self.respond_json(200, {"tags": tags})

    def challenge(self, epc):
        epc = str(epc).strip().upper()
        if not epc or len(epc) > EPC_LENGTH_LIMIT or len(epc) % 2 or any(c not in "0123456789ABCDEF" for c in epc):
            self.respond_json(400, {"error": "invalid EPC"})
            return
        try:
            payload = fetch_json(f"{REGISTRATION_API_BASE}/v1/registration-challenges/pending")
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
            self.respond_json(503, {"error": f"registration service unavailable: {error}"})
            return
        challenge = next((item for item in payload.get("challenges", [])
                          if str(item.get("epc", "")).upper() == epc), None)
        if challenge is None:
            self.respond_json(200, {"epc": epc, "challenge": None})
            return
        expires = challenge.get("expiresAt")
        expired = False
        if expires:
            try:
                expired = datetime.fromisoformat(expires.replace("Z", "+00:00")) <= datetime.now(timezone.utc)
            except (TypeError, ValueError):
                pass
        claim_url = challenge.get("claimUrl") or challenge.get("ott") or ""
        result = {
            "epc": epc,
            "challenge": {
                "epc": str(challenge.get("epc", "")).upper(),
                "claimUrl": claim_url,
                "expiresAt": expires,
                "expired": expired,
            } if claim_url else None,
        }
        self.respond_json(200, result)

    def qr(self, value):
        if not value or len(value) > 1200:
            self.respond(400, "text/plain; charset=utf-8", b"invalid QR content")
            return
        code = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=8, border=4)
        code.add_data(value)
        code.make(fit=True)
        svg = code.make_image(image_factory=SvgPathImage).to_string()
        self.respond(200, "image/svg+xml; charset=utf-8", svg)

    def respond_json(self, status, payload):
        self.respond(status, "application/json; charset=utf-8",
                     json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    def respond(self, status, content_type, body):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format, *_args):
        pass


if __name__ == "__main__":
    print(f"QR website: http://127.0.0.1:{PORT}/qr.html", flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
