#!/usr/bin/env python3

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ART_DIR = PROJECT_ROOT / "art"
MANIFEST_PATH = ART_DIR / "manifest.json"
CHUNK_DIR_NAME = "manifest-chunks"
CHUNK_SIZE = 500
REASONING_PREVIEW_LENGTH = 360


def unique_colors(pixels: list[dict[str, Any]]) -> list[str]:
    colors: list[str] = []
    seen: set[str] = set()

    for pixel in pixels:
        color = str(pixel.get("color", "")).strip().upper()

        if color and color not in seen:
            seen.add(color)
            colors.append(color)

    return colors


def gallery_record(art_dir: Path, artwork_id: str) -> dict[str, Any]:
    record_path = art_dir / f"{artwork_id}.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    pixels = record.get("pixels") if isinstance(record.get("pixels"), list) else []
    reasoning = str(record.get("reasoning", ""))

    return {
        "id": artwork_id,
        "title": record.get("title", ""),
        "seed": record.get("seed", ""),
        "reasoning": reasoning[:REASONING_PREVIEW_LENGTH],
        "size": record.get("size", {"width": 8, "height": 8}),
        "colors": unique_colors(pixels),
    }


def build_gallery_manifest(art_dir: Path = ART_DIR, manifest_path: Path = MANIFEST_PATH) -> dict[str, Any]:
    art_dir.mkdir(parents=True, exist_ok=True)
    chunk_dir = art_dir / CHUNK_DIR_NAME

    if chunk_dir.exists():
        shutil.rmtree(chunk_dir)

    chunk_dir.mkdir(parents=True, exist_ok=True)

    json_ids = {path.stem for path in art_dir.glob("*.json") if path.name != manifest_path.name}
    svg_ids = {path.stem for path in art_dir.glob("*.svg")}
    artwork_ids = sorted(
        json_ids & svg_ids,
        key=lambda artwork_id: (
            max((art_dir / f"{artwork_id}.json").stat().st_mtime, (art_dir / f"{artwork_id}.svg").stat().st_mtime),
            artwork_id,
        ),
        reverse=True,
    )
    chunks = []

    for chunk_index, start in enumerate(range(0, len(artwork_ids), CHUNK_SIZE)):
        chunk_ids = artwork_ids[start:start + CHUNK_SIZE]
        records = [gallery_record(art_dir, artwork_id) for artwork_id in chunk_ids]
        chunk_path = chunk_dir / f"{chunk_index:05d}.json"
        chunk_path.write_text(json.dumps({"records": records}, separators=(",", ":")) + "\n", encoding="utf-8")
        chunks.append({
            "path": f"art/{CHUNK_DIR_NAME}/{chunk_path.name}",
            "count": len(records),
            "start": start,
        })

    manifest = {
        "artworkIds": artwork_ids,
        "count": len(artwork_ids),
        "chunkSize": CHUNK_SIZE,
        "chunks": chunks,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    manifest = build_gallery_manifest()
    print(f"Wrote {MANIFEST_PATH.relative_to(PROJECT_ROOT)} with {manifest['count']} artworks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
