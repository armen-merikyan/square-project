#!/usr/bin/env python3
"""Local no-cache static server with browser reload on file changes."""

from __future__ import annotations

import argparse
import mimetypes
import os
import time
import urllib.parse
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
