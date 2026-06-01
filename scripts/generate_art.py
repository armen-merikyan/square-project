#!/usr/bin/env python3

"""
Local-only design-time generator for Square Project art.

This script reads the OpenAI API key from the local .env file, asks OpenAI for
structured 8x8 pixel art JSON, validates the result, checks for duplicate pixel
arrangements, and writes the generated JSON and SVG files to ./art.

Do not run this from browser code or a public server.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import random
import re
import ssl
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock
from typing import Any
from xml.sax.saxutils import escape

from build_gallery_manifest import build_gallery_manifest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ART_DIR = PROJECT_ROOT / "art"
ENV_PATH = PROJECT_ROOT / ".env"
SEED_LIBRARY_PATH = PROJECT_ROOT / "scripts" / "seed.json"
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
REQUEST_TIMEOUT_SECONDS = 30
MAX_ATTEMPTS = 3
MAX_BATCH_FAILURES_MULTIPLIER = 3


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate local 8x8 Square Project pixel art from a text seed."
    )
    parser.add_argument(
        "-c",
        "--count",
        type=int,
        default=1,
        help="Number of unique artworks to generate from the seed.",
    )
    parser.add_argument(
        "-p",
        "--parallel",
        type=int,
        default=5,
        help="Number of OpenAI requests to run at the same time.",
    )
    parser.add_argument(
        "--seed-library",
        type=Path,
        default=SEED_LIBRARY_PATH,
        help="JSON library of emotions, layouts, palettes, and pattern constraints.",
    )
    parser.add_argument(
        "--no-seed-library",
        action="store_true",
        help="Use only the freeform text seed and skip scripts/seed.json art direction.",
    )
    parser.add_argument("seed", nargs="+", help="Text seed to guide the generated pixel art.")
    args = parser.parse_args()

    if args.count < 1:
        print("--count must be 1 or greater", file=sys.stderr)
        return 1
    if args.parallel < 1:
        print("--parallel must be 1 or greater", file=sys.stderr)
        return 1

    seed_text = " ".join(args.seed).strip()
    env = load_env(ENV_PATH)
    api_key = os.environ.get("OPENAI_API_KEY") or env.get("OPENAI_API_KEY")
    model = env.get("OPENAI_MODEL", "gpt-4o-mini")

    if not api_key:
        print("Missing OPENAI_API_KEY in local .env", file=sys.stderr)
        return 1

    ART_DIR.mkdir(parents=True, exist_ok=True)

    seed_library = None
    if not args.no_seed_library:
        seed_library = load_seed_library(args.seed_library)
        if seed_library:
            print(f"Loaded seed library: {args.seed_library}", flush=True)
        else:
            print(f"No seed library loaded from {args.seed_library}; using text seed only.", flush=True)

    existing_hashes = load_existing_hashes(ART_DIR)
    created = 0
    batch_failures = 0
    generation_attempt = 0
    max_batch_failures = args.count * MAX_BATCH_FAILURES_MULTIPLIER
    hash_lock = Lock()

    exit_code = 0

    try:
        with ThreadPoolExecutor(max_workers=args.parallel) as executor:
            while created < args.count:
                remaining = args.count - created
                futures = []

                for _ in range(remaining):
                    generation_attempt += 1
                    iteration_seed = seed_text
                    if args.count > 1:
                        iteration_seed = (
                            f"{seed_text} | abstract variation request {generation_attempt}; "
                            f"target batch count {args.count}"
                        )

                    print(
                        f"Queueing request {generation_attempt} ({created}/{args.count} created)...",
                        flush=True,
                    )
                    futures.append(
                        executor.submit(
                            generate_one,
                            api_key=api_key,
                            model=model,
                            seed_text=iteration_seed,
                            seed_library=seed_library,
                            existing_hashes=existing_hashes,
                            hash_lock=hash_lock,
                        )
                    )

                for future in as_completed(futures):
                    try:
                        if future.result():
                            created += 1
                            print(f"Progress: {created}/{args.count} created.", flush=True)
                    except (RuntimeError, TimeoutError, urllib.error.URLError) as error:
                        batch_failures += 1
                        print(f"Generation failed: {error}", file=sys.stderr, flush=True)
                        if batch_failures >= max_batch_failures:
                            print(
                                f"Stopped after {batch_failures} failed generation attempts.",
                                file=sys.stderr,
                                flush=True,
                            )
                            exit_code = 1
                            return exit_code

        print(f"Generated {created} unique artwork{'s' if created != 1 else ''}.", flush=True)
        return exit_code
    finally:
        manifest = build_gallery_manifest()
        print(
            f"Updated art/manifest.json with {manifest['count']} artworks.",
            flush=True,
        )


def generate_one(
    api_key: str,
    model: str,
    seed_text: str,
    seed_library: dict[str, Any] | None,
    existing_hashes: set[str],
    hash_lock: Lock,
) -> bool:
    generation_spec = build_generation_spec(seed_text, seed_library)
    generated = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            generated = request_pixel_art(
                api_key=api_key,
                model=model,
                seed_text=seed_text,
                generation_spec=generation_spec,
                requested_id="pending-content-key",
            )
            break
        except TimeoutError as error:
            if attempt == MAX_ATTEMPTS:
                raise
            print(f"{error} Retrying {attempt + 1}/{MAX_ATTEMPTS}...", file=sys.stderr, flush=True)

    if generated is None:
        raise RuntimeError("OpenAI request did not return a response.")
    art = normalize_and_validate_art(generated, seed_text)
    if generation_spec:
        art["generationSpec"] = generation_spec
    art_key = hash_pixels(art["pixels"])

    with hash_lock:
        if art_key in existing_hashes:
            print("Duplicate pixel arrangement detected. No files were written.", file=sys.stderr, flush=True)
            print(f"Seed: {seed_text}", file=sys.stderr, flush=True)
            return False
        existing_hashes.add(art_key)

    art["id"] = art_key
    art["key"] = art_key
    art["pixelHash"] = art_key
    art["jsonFile"] = f"{art_key}.json"
    art["svgFile"] = f"{art_key}.svg"
    art["createdAt"] = dt.datetime.now(dt.UTC).isoformat()

    json_path = ART_DIR / art["jsonFile"]
    svg_path = ART_DIR / art["svgFile"]

    json_path.write_text(json.dumps(art, indent=2) + "\n", encoding="utf-8")
    svg_path.write_text(render_svg(art), encoding="utf-8")

    print(f"Created {json_path.relative_to(PROJECT_ROOT)}", flush=True)
    print(f"Created {svg_path.relative_to(PROJECT_ROOT)}", flush=True)
    return True


def load_env(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        value = value.strip().strip("'\"")
        values[key.strip()] = value

    return values


def load_seed_library(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None

    try:
        library = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"Seed library is not valid JSON: {path}") from error

    if not isinstance(library, dict):
        raise ValueError(f"Seed library must be a JSON object: {path}")

    return library


def build_generation_spec(seed_text: str, library: dict[str, Any] | None) -> dict[str, Any] | None:
    if not library:
        return None

    rng = random.Random(hashlib.sha256(seed_text.encode("utf-8")).hexdigest())
    emotion_pair = choose_emotion_pair(rng, library, seed_text)
    emotion_a = str(emotion_pair[0]) if len(emotion_pair) > 0 else "curiosity"
    emotion_b = str(emotion_pair[1]) if len(emotion_pair) > 1 else "peace"
    palette = choose_palette(rng, library, emotion_a, emotion_b)
    composition = choose_composition(rng, library, emotion_a, emotion_b)

    return {
        "emotionPair": [emotion_a, emotion_b],
        "emotionMoods": {
            emotion_a: choose_many(rng, library.get("visual_moods", {}).get(emotion_a), 3),
            emotion_b: choose_many(rng, library.get("visual_moods", {}).get(emotion_b), 3),
        },
        "layout": choose_named(rng, library.get("8x8_layout_templates")),
        "flow": choose(rng, library.get("flows"), "center_outward"),
        "patterns": {
            emotion_a: choose(rng, library.get("pattern_types"), "grid"),
            emotion_b: choose(rng, library.get("pattern_types"), "noise"),
        },
        "edgeStyle": choose(rng, library.get("edge_styles"), "hard_edges"),
        "contrastType": choose(rng, library.get("contrast_types"), "light_vs_dark"),
        "shapeSeed": choose(rng, library.get("shape_seeds"), "single_pixel"),
        "composition": composition,
        "palette": palette,
        "referenceExample": choose_reference_example(rng, library, emotion_a, emotion_b),
        "generationRules": [str(rule) for rule in library.get("random_generation_rules", [])],
        "brokenPixels": rng.randint(1, 6),
        "negativeSpaceRule": (
            "Leave at least 10 percent negative space unless the chosen emotional tone needs dense pressure."
        ),
    }


def choose_emotion_pair(rng: random.Random, library: dict[str, Any], seed_text: str) -> Any:
    contrasts = library.get("emotional_contrasts")
    if not isinstance(contrasts, list) or not contrasts:
        return ["curiosity", "peace"]

    seed_lower = seed_text.lower()
    known_emotions = set(str(emotion).lower() for emotion in library.get("emotions", []))
    for contrast in contrasts:
        if isinstance(contrast, list):
            known_emotions.update(str(emotion).lower() for emotion in contrast)

    mentioned = {
        emotion
        for emotion in known_emotions
        if re.search(rf"\b{re.escape(emotion)}\b", seed_lower)
    }

    if len(mentioned) >= 2:
        exact_matches = [
            contrast
            for contrast in contrasts
            if isinstance(contrast, list)
            and len(contrast) >= 2
            and {str(contrast[0]).lower(), str(contrast[1]).lower()} <= mentioned
        ]
        if exact_matches:
            return rng.choice(exact_matches)

    if mentioned:
        partial_matches = [
            contrast
            for contrast in contrasts
            if isinstance(contrast, list)
            and any(str(emotion).lower() in mentioned for emotion in contrast)
        ]
        if partial_matches:
            return rng.choice(partial_matches)

    return choose(rng, contrasts, ["curiosity", "peace"])


def choose(rng: random.Random, values: Any, fallback: Any) -> Any:
    if isinstance(values, list) and values:
        return rng.choice(values)
    return fallback


def choose_many(rng: random.Random, values: Any, count: int) -> list[str]:
    if not isinstance(values, list) or not values:
        return []
    sample_size = min(count, len(values))
    return [str(value) for value in rng.sample(values, sample_size)]


def choose_named(rng: random.Random, values: Any) -> dict[str, str]:
    value = choose(rng, values, {"name": "argument_grid", "description": "Two patterns fight for control."})
    if isinstance(value, dict):
        return {
            "name": str(value.get("name") or "argument_grid"),
            "description": str(value.get("description") or ""),
        }
    return {"name": str(value), "description": ""}


def choose_palette(rng: random.Random, library: dict[str, Any], emotion_a: str, emotion_b: str) -> dict[str, Any]:
    palettes = library.get("color_palettes")
    if not isinstance(palettes, list) or not palettes:
        return {"name": "model_selected", "colors": []}

    pair_tokens = {emotion_a.lower(), emotion_b.lower()}
    matching = []
    for palette in palettes:
        if not isinstance(palette, dict):
            continue
        name_tokens = set(str(palette.get("name", "")).lower().split("_"))
        if pair_tokens & name_tokens:
            matching.append(palette)

    selected = rng.choice(matching or palettes)
    return {
        "name": str(selected.get("name") or "unnamed_palette"),
        "colors": [str(color) for color in selected.get("colors", [])],
    }


def choose_composition(rng: random.Random, library: dict[str, Any], emotion_a: str, emotion_b: str) -> dict[str, Any]:
    arguments = library.get("compositional_arguments")
    if not isinstance(arguments, list) or not arguments:
        return {"name": "emotion_vs_emotion", "idea": "Two emotional patterns compete inside the grid."}

    pair_key = f"{emotion_a}_vs_{emotion_b}".lower()
    reverse_pair_key = f"{emotion_b}_vs_{emotion_a}".lower()
    matching = []
    for argument in arguments:
        if not isinstance(argument, dict):
            continue
        good_for = [str(value).lower() for value in argument.get("good_for", [])]
        if pair_key in good_for or reverse_pair_key in good_for or emotion_a.lower() in good_for or emotion_b.lower() in good_for:
            matching.append(argument)

    selected = rng.choice(matching or arguments)
    return {
        "name": str(selected.get("name") or "emotion_vs_emotion"),
        "idea": str(selected.get("idea") or "Two emotional patterns compete inside the grid."),
    }


def choose_reference_example(
    rng: random.Random,
    library: dict[str, Any],
    emotion_a: str,
    emotion_b: str,
) -> dict[str, Any] | None:
    examples = library.get("example_combinations")
    if not isinstance(examples, list) or not examples:
        return None

    pair_tokens = {emotion_a.lower(), emotion_b.lower()}
    matching = []
    for example in examples:
        if not isinstance(example, dict):
            continue
        example_pair = {str(emotion).lower() for emotion in example.get("emotion_pair", [])}
        if pair_tokens & example_pair:
            matching.append(example)

    selected = rng.choice(matching or examples)
    return {
        "title": str(selected.get("title") or "Untitled reference"),
        "emotionPair": [str(emotion) for emotion in selected.get("emotion_pair", [])],
        "layout": str(selected.get("layout") or ""),
        "flow": str(selected.get("flow") or ""),
        "pattern": str(selected.get("pattern") or ""),
        "edge": str(selected.get("edge") or ""),
        "shape": str(selected.get("shape") or ""),
        "palette": str(selected.get("palette") or ""),
    }


def generation_spec_text(spec: dict[str, Any] | None) -> str:
    if not spec:
        return "No local seed library constraints were provided."

    return json.dumps(spec, indent=2, sort_keys=True)


def request_pixel_art(
    api_key: str,
    model: str,
    seed_text: str,
    generation_spec: dict[str, Any] | None,
    requested_id: str,
) -> dict[str, Any]:
    payload = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "You create strict 8x8 abstract pixel art data for Square Project. "
                            "Return exactly 8 rows, each with 8 valid 6-digit hex colors. "
                            "Do not try to draw "
                            "literal objects, icons, scenes, faces, buildings, landscapes, or "
                            "recognizable pictures. Treat every seed as an emotional score, not "
                            "a subject list. Create pattern, pressure, contrast, collision, echo, "
                            "interruption, quiet, density, and release through color placement. "
                            "The result must be unique, intentional, and suitable as abstract "
                            "8x8 square art."
                        ),
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": f"""Seed text: {seed_text}
Requested ID: {requested_id}

Create an abstract 8x8 color composition. Before choosing pixels, translate the seed into emotional tone, pattern logic, contrast, and collisions of feeling. Do not treat the seed as an object to draw.

Local seed library art direction:
{generation_spec_text(generation_spec)}

Use the local seed library art direction as concrete constraints for the composition: emotion pair, layout, flow, pattern types, edge style, contrast type, palette family, broken pixels, and negative space. The final square should still be abstract and should not draw a literal icon for the shape seed.

If the seed contains concrete nouns, convert them into abstract qualities:
- city becomes compression, glow, grid pressure, signal noise, or waking density
- ocean becomes depth, drift, hidden weight, shimmer, or slow pull
- moon becomes distance, quiet contrast, pale interruption, or suspended light
- forest becomes layered density, hidden path, damp calm, or organic rhythm
- robot becomes precision, metallic restraint, repetition, or a sudden human warmth

Use color, contrast, and placement to suggest a story or feeling. Prefer visual ideas like:
- warm vs cool emotional tension
- quiet space against dense clusters
- a shift from calm to pressure
- interruption, echo, balance, or unresolved motion
- collision between bright accents and muted fields
- repeated marks that feel like memory, pulse, static, grief, joy, friction, or relief
- asymmetric patterns where one color interrupts another

Avoid literal representation. Do not make symbols, characters, scenery, icons, or small illustrations. The square should read as a pattern of emotion and contrast first.

Include concise reasoning explaining the emotional tone, why you picked the palette, where the main contrast or collision happens, and how the seed shaped the abstract pattern.

Expected JSON object shape:
{{
  "id": "{requested_id}",
  "seed": "{seed_text}",
  "title": "Short abstract artwork title",
  "reasoning": "Emotional tone, palette logic, contrast/collision, and how the seed became an abstract pattern.",
  "size": {{ "width": 8, "height": 8 }},
  "rows": [
    ["#000000", "#111111", "#222222", "#333333", "#444444", "#555555", "#666666", "#777777"],
    ["#FFFFFF", "#EEEEEE", "#DDDDDD", "#CCCCCC", "#BBBBBB", "#AAAAAA", "#999999", "#888888"]
  ]
}}

The final rows array must include exactly 8 rows, and each row must include exactly 8 colors.""",
                    }
                ],
            },
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "square_pixel_art",
                "strict": True,
                "schema": pixel_art_schema(),
            }
        },
    }

    request = urllib.request.Request(
        OPENAI_RESPONSES_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=REQUEST_TIMEOUT_SECONDS,
            context=ssl_context(),
        ) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except TimeoutError as error:
        raise TimeoutError(f"OpenAI request timed out after {REQUEST_TIMEOUT_SECONDS}s.") from error
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI request failed: {body}") from error

    output_text = response_payload.get("output_text") or extract_output_text(response_payload)
    if not output_text:
        raise RuntimeError(f"OpenAI response did not include output text: {response_payload}")

    return json.loads(output_text)


def ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def pixel_art_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["id", "seed", "title", "reasoning", "size", "rows"],
        "properties": {
            "id": {"type": "string", "description": "The requested collection ID."},
            "seed": {"type": "string", "description": "The seed text used to guide the abstract artwork."},
            "title": {"type": "string", "description": "A short title for the abstract 8x8 artwork."},
            "reasoning": {
                "type": "string",
                "description": (
                    "Concise explanation of the color choices, contrast, rhythm, and abstract "
                    "story carried by the pixel arrangement."
                ),
            },
            "size": {
                "type": "object",
                "additionalProperties": False,
                "required": ["width", "height"],
                "properties": {
                    "width": {"type": "integer", "enum": [8]},
                    "height": {"type": "integer", "enum": [8]},
                },
            },
            "rows": {
                "type": "array",
                "minItems": 8,
                "maxItems": 8,
                "items": {
                    "type": "array",
                    "minItems": 8,
                    "maxItems": 8,
                    "items": {
                        "type": "string",
                        "pattern": "^#[0-9A-Fa-f]{6}$",
                        "description": "A 6-digit hex color code.",
                    },
                },
            },
        },
    }


def extract_output_text(payload: dict[str, Any]) -> str:
    chunks: list[str] = []
    for item in payload.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text":
                chunks.append(content.get("text", ""))
    return "".join(chunks)


def pixels_from_rows(rows: Any) -> list[dict[str, Any]]:
    if not isinstance(rows, list) or len(rows) != 8:
        raise ValueError("Generated rows must contain exactly 8 rows.")

    pixels: list[dict[str, Any]] = []
    for y, row in enumerate(rows):
        if not isinstance(row, list) or len(row) != 8:
            raise ValueError(f"Generated row {y} must contain exactly 8 colors.")

        for x, color in enumerate(row):
            pixels.append({"x": x, "y": y, "color": color})

    return pixels


def normalize_and_validate_art(generated: dict[str, Any], seed_text: str) -> dict[str, Any]:
    if not isinstance(generated, dict):
        raise ValueError("Generated art must be a JSON object.")

    pixels = generated.get("pixels")
    rows = generated.get("rows")
    if rows is not None:
        pixels = pixels_from_rows(rows)

    if not isinstance(pixels, list):
        raise ValueError("Generated art must include a rows or pixels array.")

    art = {
        "id": "",
        "seed": seed_text,
        "title": str(generated.get("title") or "Untitled Square").strip(),
        "reasoning": str(generated.get("reasoning") or "").strip(),
        "size": {"width": 8, "height": 8},
        "pixels": [],
    }

    if not art["reasoning"]:
        raise ValueError("Generated art is missing color and arrangement reasoning.")

    if len(pixels) != 64:
        raise ValueError(f"Expected 64 pixels, received {len(pixels)}.")

    seen: set[tuple[int, int]] = set()
    normalized_pixels: list[dict[str, Any]] = []

    for pixel in pixels:
        x = int(pixel.get("x"))
        y = int(pixel.get("y"))
        color = str(pixel.get("color", "")).upper()
        coordinate = (x, y)

        if x < 0 or x > 7:
            raise ValueError(f"Invalid x coordinate: {pixel}")
        if y < 0 or y > 7:
            raise ValueError(f"Invalid y coordinate: {pixel}")
        if not re.fullmatch(r"#[0-9A-F]{6}", color):
            raise ValueError(f"Invalid color: {pixel}")
        if coordinate in seen:
            raise ValueError(f"Duplicate pixel coordinate found: {x},{y}")

        seen.add(coordinate)
        normalized_pixels.append({"x": x, "y": y, "color": color})

    for y in range(8):
        for x in range(8):
            if (x, y) not in seen:
                raise ValueError(f"Missing pixel coordinate: {x},{y}")

    art["pixels"] = sorted(normalized_pixels, key=lambda item: (item["y"], item["x"]))
    return art


def load_existing_hashes(directory: Path) -> set[str]:
    hashes: set[str] = set()
    for json_file in directory.glob("*.json"):
        try:
            art = json.loads(json_file.read_text(encoding="utf-8"))
            hashes.add(art.get("pixelHash") or hash_pixels(art.get("pixels", [])))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            continue
    return hashes

def hash_pixels(pixels: list[dict[str, Any]]) -> str:
    stable_pixels = sorted(
        (
            {"x": int(pixel["x"]), "y": int(pixel["y"]), "color": str(pixel["color"]).upper()}
            for pixel in pixels
        ),
        key=lambda item: (item["y"], item["x"]),
    )
    encoded = json.dumps(stable_pixels, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def render_svg(art: dict[str, Any]) -> str:
    pixel_size = 32
    image_size = 8 * pixel_size
    rects = "\n".join(
        f'  <rect x="{pixel["x"] * pixel_size}" y="{pixel["y"] * pixel_size}" '
        f'width="{pixel_size}" height="{pixel_size}" fill="{pixel["color"]}" />'
        for pixel in art["pixels"]
    )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{image_size}" height="{image_size}" viewBox="0 0 {image_size} {image_size}" shape-rendering="crispEdges" role="img" aria-labelledby="title desc">
  <title id="title">{escape(str(art["title"]))}</title>
  <desc id="desc">{escape(str(art["reasoning"]))}</desc>
  <rect width="{image_size}" height="{image_size}" fill="#FFFFFF" />
{rects}
</svg>
"""


if __name__ == "__main__":
    raise SystemExit(main())
