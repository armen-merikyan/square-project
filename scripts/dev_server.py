#!/usr/bin/env python3
"""Local no-cache static server with browser reload on file changes."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import time
import urllib.parse
import urllib.request
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


WATCHED_EXTENSIONS = {
    ".css",
    ".html",
    ".js",
    ".json",
    ".svg",
}
IGNORED_DIRECTORIES = {
    ".git",
    ".venv",
    "__pycache__",
}
LIVE_RELOAD_PATH = "/__live-reload"
POLL_INTERVAL_SECONDS = 0.5
STRIPE_CHECKOUT_API_URL = "https://api.stripe.com/v1/checkout/sessions"
DEFAULT_PRINT_AMOUNT_CENTS = 2400
DEFAULT_FRAMED_AMOUNT_CENTS = 3900
CHECKOUT_VARIANTS = {
    "print": {
        "label": "8x8 Art Print",
        "price_env": "STRIPE_PRINT_PRICE_ID",
        "amount_env": "PRINT_AMOUNT_CENTS",
        "default_amount": DEFAULT_PRINT_AMOUNT_CENTS,
    },
    "framed": {
        "label": "8x8 Art Print with Black Frame",
        "price_env": "STRIPE_FRAMED_PRINT_PRICE_ID",
        "amount_env": "FRAMED_PRINT_AMOUNT_CENTS",
        "default_amount": DEFAULT_FRAMED_AMOUNT_CENTS,
    },
}


LIVE_RELOAD_SNIPPET = """
<script>
(() => {
  const events = new EventSource("/__live-reload");
  events.addEventListener("change", () => window.location.reload());
})();
</script>
"""


def iter_watched_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in IGNORED_DIRECTORIES for part in path.parts):
            continue
        if path.suffix.lower() in WATCHED_EXTENSIONS:
            yield path


def latest_mtime(root: Path) -> int:
    latest = 0

    for path in iter_watched_files(root):
        try:
            latest = max(latest, path.stat().st_mtime_ns)
        except OSError:
            continue

    return latest


class DevServerHandler(SimpleHTTPRequestHandler):
    server_version = "SquareDevServer/1.0"

    def do_POST(self):
        parsed_path = urllib.parse.urlsplit(self.path)

        if parsed_path.path == "/api/create-checkout-session":
            self.create_checkout_session()
            return

        self.send_error(HTTPStatus.NOT_FOUND, "API endpoint not found")

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def do_GET(self):
        parsed_path = urllib.parse.urlsplit(self.path)

        if parsed_path.path == LIVE_RELOAD_PATH:
            self.serve_live_reload()
            return

        if self.is_html_request(parsed_path.path):
            self.serve_html_with_live_reload(parsed_path.path)
            return

        super().do_GET()

    def is_html_request(self, request_path: str) -> bool:
        translated = Path(self.translate_path(request_path))

        if translated.is_dir():
            translated = translated / "index.html"

        return translated.suffix.lower() == ".html" and translated.is_file()

    def serve_html_with_live_reload(self, request_path: str) -> None:
        file_path = Path(self.translate_path(request_path))

        if file_path.is_dir():
            file_path = file_path / "index.html"

        try:
            content = file_path.read_text(encoding="utf-8")
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return

        if "</body>" in content:
            content = content.replace("</body>", f"{LIVE_RELOAD_SNIPPET}</body>", 1)
        else:
            content += LIVE_RELOAD_SNIPPET

        payload = content.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def serve_live_reload(self) -> None:
        root = Path(self.directory).resolve()
        last_seen = latest_mtime(root)

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        try:
            self.wfile.write(b": connected\n\n")
            self.wfile.flush()

            while True:
                time.sleep(POLL_INTERVAL_SECONDS)
                current = latest_mtime(root)

                if current > last_seen:
                    last_seen = current
                    self.wfile.write(b"event: change\ndata: reload\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return

    def read_json_body(self) -> dict:
        content_length = int(self.headers.get("Content-Length", "0"))

        if content_length <= 0:
            return {}

        body = self.rfile.read(content_length)
        return json.loads(body.decode("utf-8"))

    def send_json(self, status: HTTPStatus, payload: dict) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def create_checkout_session(self) -> None:
        load_env_file(Path(self.directory) / ".env")
        stripe_secret_key = os.environ.get("STRIPE_SECRET_KEY", "").strip()

        if not stripe_secret_key or stripe_secret_key.startswith("sk_test_your"):
            self.send_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"error": "Stripe is not configured. Set STRIPE_SECRET_KEY in .env."},
            )
            return

        try:
            payload = self.read_json_body()
            checkout_payload = build_stripe_checkout_payload(Path(self.directory), payload, self.request_origin())
            request = urllib.request.Request(
                STRIPE_CHECKOUT_API_URL,
                data=urllib.parse.urlencode(checkout_payload, doseq=True).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {stripe_secret_key}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                method="POST",
            )

            with urllib.request.urlopen(request, timeout=20) as response:
                stripe_response = json.loads(response.read().decode("utf-8"))

            self.send_json(HTTPStatus.OK, {"url": stripe_response["url"]})
        except ValueError as error:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
        except urllib.error.HTTPError as error:
            message = error.read().decode("utf-8")
            self.send_json(HTTPStatus.BAD_GATEWAY, {"error": "Stripe rejected the checkout request.", "details": message})
        except (OSError, json.JSONDecodeError, KeyError) as error:
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(error)})

    def request_origin(self) -> str:
        host = self.headers.get("Host", "127.0.0.1:8000")
        forwarded_proto = self.headers.get("X-Forwarded-Proto")
        scheme = forwarded_proto or "http"
        return f"{scheme}://{host}"

    def guess_type(self, path):
        content_type, encoding = mimetypes.guess_type(path)

        if encoding:
            return f"{content_type}; encoding={encoding}"

        return content_type or "application/octet-stream"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Square Project local dev server.")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind. Defaults to 127.0.0.1.")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind. Defaults to 8000.")
    return parser.parse_args()


def load_env_file(env_path: Path) -> None:
    if not env_path.is_file():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        if key and key not in os.environ:
            os.environ[key] = value


def build_stripe_checkout_payload(root: Path, payload: dict, origin: str) -> dict:
    artwork_id = str(payload.get("artworkId", "")).strip()
    variant = str(payload.get("variant", "")).strip()

    if not artwork_id:
        raise ValueError("Missing artworkId.")

    if variant not in CHECKOUT_VARIANTS:
        raise ValueError("Choose print or framed.")

    artwork_path = root / "art" / f"{artwork_id}.json"

    if not artwork_path.is_file():
        raise ValueError("Artwork record was not found.")

    record = json.loads(artwork_path.read_text(encoding="utf-8"))
    if record.get("id") and record["id"] != artwork_id:
        raise ValueError("Artwork record id does not match the requested id.")

    title = str(record.get("title") or "Untitled square")[:180]
    variant_config = CHECKOUT_VARIANTS[variant]
    success_url = f"{origin}/gallery.html?art={urllib.parse.quote(artwork_id)}&checkout=success"
    cancel_url = f"{origin}/gallery.html?art={urllib.parse.quote(artwork_id)}&checkout=cancelled"
    metadata = {
        "artwork_id": artwork_id,
        "artwork_title": title[:120],
        "fulfillment_type": variant,
        "size": "8x8",
        "frame": "upsimples 8x8 black frame" if variant == "framed" else "none",
    }
    checkout_payload = {
        "mode": "payment",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "client_reference_id": artwork_id,
        "shipping_address_collection[allowed_countries][0]": "US",
        "metadata[artwork_id]": metadata["artwork_id"],
        "metadata[artwork_title]": metadata["artwork_title"],
        "metadata[fulfillment_type]": metadata["fulfillment_type"],
        "metadata[size]": metadata["size"],
        "metadata[frame]": metadata["frame"],
        "payment_intent_data[metadata][artwork_id]": metadata["artwork_id"],
        "payment_intent_data[metadata][artwork_title]": metadata["artwork_title"],
        "payment_intent_data[metadata][fulfillment_type]": metadata["fulfillment_type"],
        "payment_intent_data[metadata][size]": metadata["size"],
        "payment_intent_data[metadata][frame]": metadata["frame"],
        "line_items[0][quantity]": "1",
    }
    price_id = os.environ.get(variant_config["price_env"], "").strip()

    if price_id:
        checkout_payload["line_items[0][price]"] = price_id
        return checkout_payload

    amount = int(os.environ.get(variant_config["amount_env"], variant_config["default_amount"]))
    product_name = f"Square Project {variant_config['label']}"
    product_description = f"{title}. Artwork ID {artwork_id}."

    checkout_payload.update({
        "line_items[0][price_data][currency]": "usd",
        "line_items[0][price_data][unit_amount]": str(amount),
        "line_items[0][price_data][product_data][name]": product_name,
        "line_items[0][price_data][product_data][description]": product_description[:500],
        "line_items[0][price_data][product_data][metadata][artwork_id]": metadata["artwork_id"],
        "line_items[0][price_data][product_data][metadata][fulfillment_type]": metadata["fulfillment_type"],
        "line_items[0][price_data][product_data][metadata][size]": metadata["size"],
        "line_items[0][price_data][product_data][metadata][frame]": metadata["frame"],
    })

    if not origin.startswith("http://127.0.0.1") and not origin.startswith("http://localhost"):
        checkout_payload["line_items[0][price_data][product_data][images][0]"] = (
            f"{origin}/art/{urllib.parse.quote(artwork_id)}.svg"
        )

    return checkout_payload


def main() -> None:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]

    os.chdir(root)
    handler = lambda *handler_args, **handler_kwargs: DevServerHandler(
        *handler_args,
        directory=str(root),
        **handler_kwargs,
    )

    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Serving {root}")
    print(f"Open http://{args.host}:{args.port}/")
    print("Press Ctrl-C to stop.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping dev server.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
