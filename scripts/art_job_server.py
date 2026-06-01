#!/usr/bin/env python3
"""Local-only web GUI for running Square Project art jobs."""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import random
import subprocess
import sys
import threading
import time
import urllib.parse
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from uuid import uuid4


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8010
MAX_LOG_LINES = 400
MAX_SEED_LENGTH = 500
MAX_COUNT = 200
MAX_PARALLEL = 20
SEED_LIBRARY_PATH = PROJECT_ROOT / "scripts" / "seed.json"


@dataclass
class Job:
    id: str
    kind: str
    command: list[str]
    status: str = "queued"
    created_at: str = field(default_factory=lambda: now_iso())
    started_at: str | None = None
    finished_at: str | None = None
    return_code: int | None = None
    output: list[str] = field(default_factory=list)
    process: subprocess.Popen[str] | None = None

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "command": self.command,
            "status": self.status,
            "createdAt": self.created_at,
            "startedAt": self.started_at,
            "finishedAt": self.finished_at,
            "returnCode": self.return_code,
            "output": self.output[-MAX_LOG_LINES:],
        }


class JobStore:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.jobs: dict[str, Job] = {}

    def add(self, job: Job) -> None:
        with self.lock:
            self.jobs[job.id] = job

    def get(self, job_id: str) -> Job | None:
        with self.lock:
            return self.jobs.get(job_id)

    def all(self) -> list[Job]:
        with self.lock:
            return sorted(self.jobs.values(), key=lambda job: job.created_at, reverse=True)

    def append_output(self, job_id: str, line: str) -> None:
        with self.lock:
            job = self.jobs.get(job_id)
            if not job:
                return
            job.output.append(line.rstrip("\n"))
            if len(job.output) > MAX_LOG_LINES:
                job.output = job.output[-MAX_LOG_LINES:]

    def update(self, job_id: str, **values: Any) -> None:
        with self.lock:
            job = self.jobs.get(job_id)
            if not job:
                return
            for key, value in values.items():
                setattr(job, key, value)


STORE = JobStore()


def now_iso() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


def run_job(job: Job) -> None:
    STORE.update(job.id, status="running", started_at=now_iso())
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    try:
        process = subprocess.Popen(
            job.command,
            cwd=PROJECT_ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except OSError as error:
        STORE.append_output(job.id, f"Failed to start job: {error}")
        STORE.update(job.id, status="failed", finished_at=now_iso(), return_code=1)
        return

    STORE.update(job.id, process=process)

    assert process.stdout is not None
    for line in process.stdout:
        STORE.append_output(job.id, line)

    return_code = process.wait()
    status = "completed" if return_code == 0 else "failed"
    STORE.update(
        job.id,
        status=status,
        finished_at=now_iso(),
        return_code=return_code,
        process=None,
    )


def start_job(kind: str, command: list[str]) -> Job:
    job = Job(id=uuid4().hex[:12], kind=kind, command=command)
    STORE.add(job)
    thread = threading.Thread(target=run_job, args=(job,), daemon=True)
    thread.start()
    return job


def build_generate_command(payload: dict[str, Any]) -> list[str]:
    seed = str(payload.get("seed", "")).strip()
    if bool(payload.get("useRandomSeed")) or not seed:
        seed = build_random_seed_text()
    if not seed:
        raise ValueError("Seed library could not produce a seed.")
    if len(seed) > MAX_SEED_LENGTH:
        raise ValueError(f"Seed must be {MAX_SEED_LENGTH} characters or fewer.")

    count = parse_bounded_int(payload.get("count", 1), "count", 1, MAX_COUNT)
    parallel = parse_bounded_int(payload.get("parallel", 5), "parallel", 1, MAX_PARALLEL)

    command = [
        sys.executable,
        "scripts/generate_art.py",
        "--count",
        str(count),
        "--parallel",
        str(parallel),
    ]

    if bool(payload.get("noSeedLibrary")):
        command.append("--no-seed-library")

    command.append(seed)
    return command


def load_seed_library() -> dict[str, Any]:
    try:
        library = json.loads(SEED_LIBRARY_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ValueError(f"Seed library not found: {SEED_LIBRARY_PATH}") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"Seed library is not valid JSON: {SEED_LIBRARY_PATH}") from error

    if not isinstance(library, dict):
        raise ValueError("Seed library must be a JSON object.")
    return library


def build_random_seed_text() -> str:
    library = load_seed_library()
    rng = random.SystemRandom()

    contrast = choose_seed_value(rng, library.get("emotional_contrasts"), ["curiosity", "peace"])
    if isinstance(contrast, list) and len(contrast) >= 2:
        emotion_a = str(contrast[0])
        emotion_b = str(contrast[1])
    else:
        emotions = library.get("emotions")
        emotion_a = str(choose_seed_value(rng, emotions, "curiosity"))
        emotion_b = str(choose_seed_value(rng, emotions, "peace"))

    layout = choose_seed_name(rng, library.get("8x8_layout_templates"), "argument_grid")
    flow = str(choose_seed_value(rng, library.get("flows"), "center_outward"))
    pattern_a = str(choose_seed_value(rng, library.get("pattern_types"), "grid"))
    pattern_b = str(choose_seed_value(rng, library.get("pattern_types"), "noise"))
    edge = str(choose_seed_value(rng, library.get("edge_styles"), "hard_edges"))
    contrast_type = str(choose_seed_value(rng, library.get("contrast_types"), "light_vs_dark"))
    shape = str(choose_seed_value(rng, library.get("shape_seeds"), "single_pixel"))
    palette = choose_seed_name(rng, library.get("color_palettes"), "model_selected")
    composition = choose_seed_name(rng, library.get("compositional_arguments"), "emotion_vs_emotion")

    seed = (
        f"{emotion_a} vs {emotion_b}; {composition}; {layout}; {flow}; "
        f"{pattern_a} against {pattern_b}; {edge}; {contrast_type}; "
        f"{shape}; {palette}"
    )
    return seed[:MAX_SEED_LENGTH]


def choose_seed_value(rng: random.SystemRandom, values: Any, fallback: Any) -> Any:
    if isinstance(values, list) and values:
        return rng.choice(values)
    return fallback


def choose_seed_name(rng: random.SystemRandom, values: Any, fallback: str) -> str:
    value = choose_seed_value(rng, values, fallback)
    if isinstance(value, dict):
        return str(value.get("name") or fallback)
    return str(value)


def parse_bounded_int(value: Any, name: str, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be a number.") from error

    if parsed < minimum or parsed > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}.")
    return parsed


def read_json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0") or "0")
    if length <= 0:
        return {}
    if length > 20_000:
        raise ValueError("Request body is too large.")

    raw_body = handler.rfile.read(length)
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError("Request body must be valid JSON.") from error

    if not isinstance(payload, dict):
        raise ValueError("Request body must be a JSON object.")
    return payload


class ArtJobHandler(BaseHTTPRequestHandler):
    server_version = "SquareArtJobServer/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {self.address_string()} {format % args}")

    def do_GET(self) -> None:
        parsed = urllib.parse.urlsplit(self.path)

        if parsed.path == "/":
            self.send_html(INDEX_HTML)
            return
        if parsed.path == "/api/jobs":
            self.send_json({"jobs": [job.public() for job in STORE.all()]})
            return
        if parsed.path == "/api/seeds/random":
            self.send_json({"seed": build_random_seed_text()})
            return
        if parsed.path.startswith("/api/jobs/"):
            job_id = parsed.path.rsplit("/", 1)[-1]
            job = STORE.get(job_id)
            if not job:
                self.send_json({"error": "Job not found."}, HTTPStatus.NOT_FOUND)
                return
            self.send_json({"job": job.public()})
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self) -> None:
        parsed = urllib.parse.urlsplit(self.path)

        try:
            payload = read_json_body(self)
            if parsed.path == "/api/jobs/generate":
                command = build_generate_command(payload)
                job = start_job("generate-art", command)
                self.send_json({"job": job.public()}, HTTPStatus.CREATED)
                return
            if parsed.path == "/api/jobs/manifest":
                command = [sys.executable, "scripts/build_gallery_manifest.py"]
                job = start_job("build-manifest", command)
                self.send_json({"job": job.public()}, HTTPStatus.CREATED)
                return
        except ValueError as error:
            self.send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def send_html(self, content: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        payload = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def send_json(self, data: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        payload = (json.dumps(data) + "\n").encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)


INDEX_HTML = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Square Art Jobs</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f7f7f4;
      --panel: #ffffff;
      --ink: #171717;
      --muted: #666b73;
      --line: #d8d9d3;
      --accent: #1f7a5f;
      --accent-dark: #135943;
      --danger: #a33b2f;
      --code: #111827;
    }}

    * {{
      box-sizing: border-box;
    }}

    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      font-size: 15px;
      line-height: 1.45;
    }}

    main {{
      width: min(1180px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 28px 0 40px;
    }}

    header {{
      display: flex;
      align-items: end;
      justify-content: space-between;
      gap: 20px;
      margin-bottom: 22px;
    }}

    h1, h2 {{
      margin: 0;
      letter-spacing: 0;
    }}

    h1 {{
      font-size: 28px;
      line-height: 1.1;
    }}

    h2 {{
      font-size: 17px;
    }}

    .muted {{
      color: var(--muted);
    }}

    .layout {{
      display: grid;
      grid-template-columns: minmax(280px, 380px) 1fr;
      gap: 18px;
      align-items: start;
    }}

    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 18px;
    }}

    form {{
      display: grid;
      gap: 14px;
      margin-top: 16px;
    }}

    label {{
      display: grid;
      gap: 6px;
      font-weight: 650;
    }}

    input, textarea {{
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      color: var(--ink);
      background: #fff;
      font: inherit;
      padding: 9px 10px;
    }}

    textarea {{
      min-height: 96px;
      resize: vertical;
    }}

    input:focus, textarea:focus {{
      border-color: var(--accent);
      outline: 3px solid rgba(31, 122, 95, 0.15);
    }}

    .row {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
    }}

    .checkbox {{
      display: flex;
      align-items: center;
      gap: 9px;
      font-weight: 600;
    }}

    .checkbox input {{
      width: 18px;
      height: 18px;
    }}

    .actions {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
    }}

    button {{
      min-height: 38px;
      border: 1px solid transparent;
      border-radius: 6px;
      background: var(--accent);
      color: #fff;
      cursor: pointer;
      font: inherit;
      font-weight: 700;
      padding: 8px 12px;
    }}

    button.secondary {{
      border-color: var(--line);
      background: #fff;
      color: var(--ink);
    }}

    button:hover {{
      background: var(--accent-dark);
    }}

    button.secondary:hover {{
      background: #eeeeea;
    }}

    .jobs {{
      display: grid;
      gap: 12px;
      margin-top: 16px;
    }}

    .job {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      overflow: hidden;
    }}

    .job-header {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
    }}

    .job-title {{
      display: grid;
      gap: 2px;
    }}

    .status {{
      align-self: start;
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 3px 9px;
      color: var(--muted);
      font-size: 13px;
      font-weight: 700;
      white-space: nowrap;
    }}

    .status.running {{
      border-color: #b79038;
      color: #7a5615;
      background: #fff7dd;
    }}

    .status.completed {{
      border-color: #91bea8;
      color: #1f6c53;
      background: #eef8f3;
    }}

    .status.failed {{
      border-color: #d6a29b;
      color: var(--danger);
      background: #fff1ef;
    }}

    pre {{
      margin: 0;
      max-height: 300px;
      overflow: auto;
      background: var(--code);
      color: #e7e7e7;
      padding: 13px 14px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
      line-height: 1.55;
      white-space: pre-wrap;
      word-break: break-word;
    }}

    .error {{
      min-height: 22px;
      color: var(--danger);
      font-weight: 650;
    }}

    @media (max-width: 820px) {{
      header, .layout {{
        display: grid;
      }}

      .layout, .row {{
        grid-template-columns: 1fr;
      }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Square Art Jobs</h1>
        <div class="muted">Local control panel for generator scripts only.</div>
      </div>
      <div class="muted">Project: {html.escape(PROJECT_ROOT.name)}</div>
    </header>

    <div class="layout">
      <section class="panel">
        <h2>Run Generator</h2>
        <form id="generate-form">
          <label>
            Seed
            <textarea id="seed" maxlength="{MAX_SEED_LENGTH}" placeholder="Auto-generated from scripts/seed.json"></textarea>
          </label>
          <div class="actions">
            <button class="secondary" id="random-seed-button" type="button">Random From JSON</button>
            <button class="secondary" id="clear-seed-button" type="button">Auto On Run</button>
          </div>
          <div class="row">
            <label>
              Count
              <input id="count" type="number" min="1" max="{MAX_COUNT}" value="1" required>
            </label>
            <label>
              Parallel
              <input id="parallel" type="number" min="1" max="{MAX_PARALLEL}" value="5" required>
            </label>
          </div>
          <label class="checkbox">
            <input id="no-seed-library" type="checkbox">
            Skip seed library constraints
          </label>
          <div class="actions">
            <button type="submit">Run Art Job</button>
            <button class="secondary" id="manifest-button" type="button">Rebuild Manifest</button>
          </div>
          <div class="error" id="error"></div>
        </form>
      </section>

      <section class="panel">
        <h2>Job Status</h2>
        <div class="jobs" id="jobs"></div>
      </section>
    </div>
  </main>

  <script>
    const jobsEl = document.querySelector("#jobs");
    const errorEl = document.querySelector("#error");
    const form = document.querySelector("#generate-form");
    const manifestButton = document.querySelector("#manifest-button");
    const randomSeedButton = document.querySelector("#random-seed-button");
    const clearSeedButton = document.querySelector("#clear-seed-button");
    const seedEl = document.querySelector("#seed");

    async function api(path, options = {{}}) {{
      const response = await fetch(path, {{
        headers: {{ "Content-Type": "application/json" }},
        ...options,
      }});
      const data = await response.json();
      if (!response.ok) {{
        throw new Error(data.error || "Request failed.");
      }}
      return data;
    }}

    function escapeHtml(value) {{
      return String(value).replace(/[&<>"']/g, char => ({{
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#039;",
      }}[char]));
    }}

    function renderJobs(jobs) {{
      if (!jobs.length) {{
        jobsEl.innerHTML = '<div class="muted">No jobs yet.</div>';
        return;
      }}

      jobsEl.innerHTML = jobs.map(job => {{
        const command = job.command.join(" ");
        const output = job.output.length ? job.output.join("\\n") : "Waiting for output...";
        const when = job.startedAt || job.createdAt;
        return `
          <article class="job">
            <div class="job-header">
              <div class="job-title">
                <strong>${{escapeHtml(job.kind)}} #${{escapeHtml(job.id)}}</strong>
                <span class="muted">${{escapeHtml(when)}} · code ${{job.returnCode ?? "-"}}</span>
                <span class="muted">${{escapeHtml(command)}}</span>
              </div>
              <span class="status ${{escapeHtml(job.status)}}">${{escapeHtml(job.status)}}</span>
            </div>
            <pre>${{escapeHtml(output)}}</pre>
          </article>
        `;
      }}).join("");
    }}

    async function refreshJobs() {{
      try {{
        const data = await api("/api/jobs");
        renderJobs(data.jobs);
      }} catch (error) {{
        errorEl.textContent = error.message;
      }}
    }}

    form.addEventListener("submit", async event => {{
      event.preventDefault();
      errorEl.textContent = "";
      const payload = {{
        seed: seedEl.value,
        useRandomSeed: !seedEl.value.trim(),
        count: document.querySelector("#count").value,
        parallel: document.querySelector("#parallel").value,
        noSeedLibrary: document.querySelector("#no-seed-library").checked,
      }};

      try {{
        await api("/api/jobs/generate", {{
          method: "POST",
          body: JSON.stringify(payload),
        }});
        await refreshJobs();
      }} catch (error) {{
        errorEl.textContent = error.message;
      }}
    }});

    randomSeedButton.addEventListener("click", async () => {{
      errorEl.textContent = "";
      try {{
        const data = await api("/api/seeds/random");
        seedEl.value = data.seed;
      }} catch (error) {{
        errorEl.textContent = error.message;
      }}
    }});

    clearSeedButton.addEventListener("click", () => {{
      seedEl.value = "";
      errorEl.textContent = "";
    }});

    manifestButton.addEventListener("click", async () => {{
      errorEl.textContent = "";
      try {{
        await api("/api/jobs/manifest", {{ method: "POST", body: "{{}}" }});
        await refreshJobs();
      }} catch (error) {{
        errorEl.textContent = error.message;
      }}
    }});

    api("/api/seeds/random")
      .then(data => {{
        if (!seedEl.value.trim()) {{
          seedEl.value = data.seed;
        }}
      }})
      .catch(error => {{
        errorEl.textContent = error.message;
      }});
    refreshJobs();
    window.setInterval(refreshJobs, 1500);
  </script>
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Square Project local art job GUI.")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"Host to bind. Defaults to {DEFAULT_HOST}.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Port to bind. Defaults to {DEFAULT_PORT}.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    server = ThreadingHTTPServer((args.host, args.port), ArtJobHandler)

    print(f"Serving Square Art Jobs from {PROJECT_ROOT}")
    print(f"Open http://{args.host}:{args.port}/")
    print("Press Ctrl-C to stop.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping art job server.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
