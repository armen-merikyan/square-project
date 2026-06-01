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
from urllib.error import HTTPError, URLError
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
STRIPE_CHECKOUT_PATH = "/api/stripe/checkout"
POLL_INTERVAL_SECONDS = 0.5
ARTWORK_ID_LENGTH = 64

SHOP_VARIANTS = {
    "print": {
        "label": "Art print",
        "description": "8x8 print",
        "amount": 2400,
        "price_env": "STRIPE_PRINT_PRICE_ID",
        "framed": "false",
    },
    "framed": {
        "label": "Framed print",
        "description": "8x8 print in black upsimples frame",
        "amount": 3900,
        "price_env": "STRIPE_FRAMED_PRICE_ID",
        "framed": "true",
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


def load_local_env(root: Path) -> None:
    env_path = root / ".env"

    if not env_path.is_file():
        return

    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return

    for line in lines:
        stripped = line.strip()

        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue

        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")

        if key and key not in os.environ:
            os.environ[key] = value


def is_valid_artwork_id(artwork_id: str) -> bool:
    return (
        len(artwork_id) == ARTWORK_ID_LENGTH
        and all(character in "0123456789abcdef" for character in artwork_id)
    )


def build_return_url(origin: str, return_path: str, checkout_status: str) -> str:
    parsed = urllib.parse.urlsplit(return_path or "/gallery.html")
    path = parsed.path if parsed.path.startswith("/") else "/gallery.html"

    if path.startswith("//"):
        path = "/gallery.html"

    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query = [(key, value) for key, value in query if key != "checkout"]
    query.append(("checkout", checkout_status))
    return urllib.parse.urlunsplit((
        origin,
        path,
        urllib.parse.urlencode(query),
        "",
        "",
    ))


def stripe_post(path: str, fields: dict[str, str]) -> dict:
    secret_key = os.environ.get("STRIPE_SECRET_KEY", "").strip()

    if not secret_key:
        raise RuntimeError("Set STRIPE_SECRET_KEY in .env before creating checkout.")

    payload = urllib.parse.urlencode(fields).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.stripe.com/v1/{path.lstrip('/')}",
        data=payload,
        headers={
            "Authorization": f"Bearer {secret_key}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        try:
            payload = json.loads(error.read().decode("utf-8"))
            message = payload.get("error", {}).get("message")
        except (json.JSONDecodeError, UnicodeDecodeError):
            message = None

        raise RuntimeError(message or f"Stripe returned HTTP {error.code}.") from error
    except URLError as error:
        raise RuntimeError(f"Could not reach Stripe: {error.reason}") from error


class DevServerHandler(SimpleHTTPRequestHandler):
    server_version = "SquareDevServer/1.0"

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

    def do_POST(self):
        parsed_path = urllib.parse.urlsplit(self.path)

        if parsed_path.path == STRIPE_CHECKOUT_PATH:
            self.create_stripe_checkout()
            return

        if parsed_path.path.startswith("/api/"):
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "API endpoint not found."})
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

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
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_length = 0

        if content_length <= 0 or content_length > 8192:
            raise ValueError("Invalid request body.")

        try:
            return json.loads(self.rfile.read(content_length).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ValueError("Request body must be JSON.") from error

    def send_json(self, status: HTTPStatus, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def create_stripe_checkout(self) -> None:
        try:
            payload = self.read_json_body()
            artwork_id = str(payload.get("artworkId", "")).strip()
            variant_key = str(payload.get("variant", "")).strip()

            if not is_valid_artwork_id(artwork_id):
                raise ValueError("Invalid artwork id.")

            art_file = Path(self.directory) / "art" / f"{artwork_id}.json"

            if not art_file.is_file():
                raise ValueError("Artwork record was not found.")

            variant = SHOP_VARIANTS.get(variant_key)

            if not variant:
                raise ValueError("Invalid checkout variant.")

            host = self.headers.get("Host", "127.0.0.1:8000")
            origin = f"http://{host}"
            return_path = str(payload.get("returnPath", "/gallery.html"))
            client_reference_id = str(
                payload.get("clientReferenceId", f"{artwork_id}_{variant_key}")
            )[:200]
            price_id = os.environ.get(variant["price_env"], "").strip()
            product_id = os.environ.get("STRIPE_ART_PRODUCT_ID", "").strip()

            fields = {
                "mode": "payment",
                "client_reference_id": client_reference_id,
                "success_url": build_return_url(origin, return_path, "success"),
                "cancel_url": build_return_url(origin, return_path, "cancelled"),
                "line_items[0][quantity]": "1",
                "metadata[artwork_id]": artwork_id,
                "metadata[variant]": variant_key,
                "metadata[framed]": variant["framed"],
                "payment_intent_data[metadata][artwork_id]": artwork_id,
                "payment_intent_data[metadata][variant]": variant_key,
                "payment_intent_data[metadata][framed]": variant["framed"],
                "shipping_address_collection[allowed_countries][0]": "US",
                "billing_address_collection": "auto",
            }

            if price_id:
                fields["line_items[0][price]"] = price_id
            elif product_id:
                fields.update({
                    "line_items[0][price_data][currency]": "usd",
                    "line_items[0][price_data][product]": product_id,
                    "line_items[0][price_data][unit_amount]": str(variant["amount"]),
                })
            else:
                raise RuntimeError(
                    "Set STRIPE_ART_PRODUCT_ID or Stripe Price IDs in .env before checkout."
                )

            session = stripe_post("checkout/sessions", fields)
            self.send_json(HTTPStatus.OK, {"url": session["url"], "id": session["id"]})
        except ValueError as error:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
        except RuntimeError as error:
            self.send_json(HTTPStatus.BAD_GATEWAY, {"error": str(error)})

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


def main() -> None:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    load_local_env(root)

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
