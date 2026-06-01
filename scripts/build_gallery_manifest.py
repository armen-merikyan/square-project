#!/usr/bin/env python3

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ART_DIR = PROJECT_ROOT / "art"
MANIFEST_PATH = ART_DIR / "manifest.json"
HOMEPAGE_ARTWORK_IDS_PATH = ART_DIR / "homepage-artwork-ids.json"
CHUNK_DIR_NAME = "manifest-chunks"
CATEGORY_DIR_NAME = "category-chunks"
CHUNK_SIZE = 500
CATEGORY_SIZE = 200
REASONING_PREVIEW_LENGTH = 360
COLOR_SIMILARITY_THRESHOLDS = list(range(0, 97, 8))
COLOR_FILTER_RENDER_LIMIT = 600


def normalize_color(color: Any) -> str:
    return str(color or "").strip().upper()


def unique_colors(pixels: list[dict[str, Any]]) -> list[str]:
    colors: list[str] = []
    seen: set[str] = set()

    for pixel in pixels:
        color = normalize_color(pixel.get("color", ""))

        if color and color not in seen:
            seen.add(color)
            colors.append(color)

    return colors


def record_search_text(record: dict[str, Any], colors: list[str]) -> str:
    return " ".join(
        str(value)
        for value in [
            record.get("id", ""),
            record.get("title", ""),
            record.get("seed", ""),
            record.get("reasoning", ""),
            *colors,
        ]
        if value
    ).lower()


def parse_hex_color(color: str) -> tuple[int, int, int] | None:
    normalized = normalize_color(color)

    if len(normalized) != 7 or not normalized.startswith("#"):
        return None

    try:
        return (
            int(normalized[1:3], 16),
            int(normalized[3:5], 16),
            int(normalized[5:7], 16),
        )
    except ValueError:
        return None


def color_distance(color_a: str, color_b: str) -> float:
    rgb_a = parse_hex_color(color_a)
    rgb_b = parse_hex_color(color_b)

    if rgb_a is None or rgb_b is None:
        return 0 if color_a == color_b else float("inf")

    return sum((channel_a - channel_b) ** 2 for channel_a, channel_b in zip(rgb_a, rgb_b)) ** 0.5


def color_usage(records: list[dict[str, Any]]) -> list[tuple[str, int]]:
    usage: dict[str, int] = {}

    for record in records:
        for color in record.get("colors", []):
            usage[color] = usage.get(color, 0) + 1

    return sorted(usage.items(), key=lambda item: (-item[1], item[0]))


def bucket_key(colors: list[str]) -> str:
    return "|".join(colors)


def build_color_buckets(records: list[dict[str, Any]], threshold: int) -> list[dict[str, Any]]:
    buckets: list[dict[str, Any]] = []
    representative_rgbs: list[tuple[int, int, int] | None] = []
    bucket_grid: dict[tuple[int, int, int], list[int]] = {}
    cell_size = max(threshold, 1)

    for color, count in color_usage(records):
        closest_bucket: dict[str, Any] | None = None
        closest_distance = float("inf")
        color_rgb = parse_hex_color(color)
        candidate_indexes: list[int]

        if color_rgb is None:
            candidate_indexes = list(range(len(buckets)))
        elif threshold == 0:
            candidate_indexes = bucket_grid.get(color_rgb, [])
        else:
            cell = tuple(channel // cell_size for channel in color_rgb)
            candidate_indexes = []

            for red_offset in (-1, 0, 1):
                for green_offset in (-1, 0, 1):
                    for blue_offset in (-1, 0, 1):
                        candidate_indexes.extend(bucket_grid.get((
                            cell[0] + red_offset,
                            cell[1] + green_offset,
                            cell[2] + blue_offset,
                        ), []))

        for bucket_index in candidate_indexes:
            representative_rgb = representative_rgbs[bucket_index]

            if color_rgb is not None and representative_rgb is not None:
                distance = sum(
                    (channel_a - channel_b) ** 2
                    for channel_a, channel_b in zip(color_rgb, representative_rgb)
                ) ** 0.5
            else:
                distance = color_distance(color, buckets[bucket_index]["representative"])

            if distance <= threshold and distance < closest_distance:
                closest_bucket = buckets[bucket_index]
                closest_distance = distance

        if closest_bucket is not None:
            closest_bucket["colors"].append(color)
            closest_bucket["count"] += count
            continue

        buckets.append({
            "representative": color,
            "colors": [color],
            "count": count,
        })
        representative_rgbs.append(color_rgb)

        if color_rgb is not None:
            grid_key = color_rgb if threshold == 0 else tuple(channel // cell_size for channel in color_rgb)
            bucket_grid.setdefault(grid_key, []).append(len(buckets) - 1)

    for bucket in buckets:
        bucket["colors"].sort()
        bucket["key"] = bucket_key(bucket["colors"])
        bucket["count"] = 0

    color_to_bucket_key: dict[str, str] = {}
    for bucket in buckets:
        for color in bucket["colors"]:
            color_to_bucket_key[color] = bucket["key"]

    bucket_by_key = {bucket["key"]: bucket for bucket in buckets}
    for record in records:
        matched_bucket_keys = {
            color_to_bucket_key[color]
            for color in record.get("colors", [])
            if color in color_to_bucket_key
        }

        for key in matched_bucket_keys:
            bucket_by_key[key]["count"] += 1

    buckets.sort(
        key=lambda bucket: (
            -bucket["count"],
            -len(bucket["colors"]),
            bucket["representative"],
        )
    )
    return buckets


def gallery_record(art_dir: Path, artwork_id: str) -> dict[str, Any]:
    record_path = art_dir / f"{artwork_id}.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    pixels = record.get("pixels") if isinstance(record.get("pixels"), list) else []
    reasoning = str(record.get("reasoning", ""))
    colors = unique_colors(pixels)
    gallery_record_data = {
        "id": artwork_id,
        "title": record.get("title", ""),
        "seed": record.get("seed", ""),
        "reasoning": reasoning[:REASONING_PREVIEW_LENGTH],
        "size": record.get("size", {"width": 8, "height": 8}),
        "colors": colors,
    }
    gallery_record_data["searchText"] = record_search_text(gallery_record_data, colors)

    return gallery_record_data


def build_gallery_manifest(art_dir: Path = ART_DIR, manifest_path: Path = MANIFEST_PATH) -> dict[str, Any]:
    art_dir.mkdir(parents=True, exist_ok=True)
    chunk_dir = art_dir / CHUNK_DIR_NAME
    category_dir = art_dir / CATEGORY_DIR_NAME

    if chunk_dir.exists():
        shutil.rmtree(chunk_dir)

    if category_dir.exists():
        shutil.rmtree(category_dir)

    chunk_dir.mkdir(parents=True, exist_ok=True)
    category_dir.mkdir(parents=True, exist_ok=True)

    manifest_names = {manifest_path.name, HOMEPAGE_ARTWORK_IDS_PATH.name}
    json_ids = {path.stem for path in art_dir.glob("*.json") if path.name not in manifest_names}
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
    categories = []
    all_records = [gallery_record(art_dir, artwork_id) for artwork_id in artwork_ids]
    color_indexes: dict[str, list[dict[str, Any]]] = {}
    color_index_totals: dict[str, int] = {}

    for threshold in COLOR_SIMILARITY_THRESHOLDS:
        buckets = build_color_buckets(all_records, threshold)
        color_indexes[str(threshold)] = buckets[:COLOR_FILTER_RENDER_LIMIT]
        color_index_totals[str(threshold)] = len(buckets)

    for chunk_index, start in enumerate(range(0, len(artwork_ids), CHUNK_SIZE)):
        records = all_records[start:start + CHUNK_SIZE]
        chunk_path = chunk_dir / f"{chunk_index:05d}.json"
        chunk_path.write_text(json.dumps({"records": records}, separators=(",", ":")) + "\n", encoding="utf-8")
        chunks.append({
            "path": f"art/{CHUNK_DIR_NAME}/{chunk_path.name}",
            "count": len(records),
            "start": start,
        })

    title_sorted_records = sorted(
        all_records,
        key=lambda record: (
            str(record.get("title", "")).casefold(),
            str(record.get("id", "")),
        ),
    )
    category_label_counts: dict[str, int] = {}

    for category_index, start in enumerate(range(0, len(title_sorted_records), CATEGORY_SIZE)):
        records = title_sorted_records[start:start + CATEGORY_SIZE]
        category_path = category_dir / f"{category_index:05d}.json"
        category_path.write_text(json.dumps({"records": records}, separators=(",", ":")) + "\n", encoding="utf-8")

        first_title = str(records[0].get("title") or "Untitled")
        last_title = str(records[-1].get("title") or "Untitled")
        first_letter = next((character.upper() for character in first_title if character.isalnum()), "#")
        last_letter = next((character.upper() for character in last_title if character.isalnum()), "#")
        title_range = first_letter if first_letter == last_letter else f"{first_letter}-{last_letter}"
        label_base = f"{title_range} titles"
        category_label_counts[label_base] = category_label_counts.get(label_base, 0) + 1
        label = label_base if category_label_counts[label_base] == 1 else f"{label_base}, part {category_label_counts[label_base]}"

        categories.append({
            "id": f"title-{category_index:03d}",
            "label": label,
            "description": f"{first_title} to {last_title}",
            "path": f"art/{CATEGORY_DIR_NAME}/{category_path.name}",
            "count": len(records),
            "ids": [str(record.get("id", "")) for record in records],
        })

    manifest = {
        "artworkIds": artwork_ids,
        "count": len(artwork_ids),
        "chunkSize": CHUNK_SIZE,
        "chunks": chunks,
        "categorySize": CATEGORY_SIZE,
        "categories": categories,
        "indexes": {
            "colorSimilarityThresholds": COLOR_SIMILARITY_THRESHOLDS,
            "colorBuckets": color_indexes,
            "colorBucketTotals": color_index_totals,
        },
    }
    manifest_path.write_text(json.dumps(manifest, separators=(",", ":")) + "\n", encoding="utf-8")
    HOMEPAGE_ARTWORK_IDS_PATH.write_text(
        json.dumps({"artworkIds": artwork_ids, "count": len(artwork_ids)}, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    manifest = build_gallery_manifest()
    print(f"Wrote {MANIFEST_PATH.relative_to(PROJECT_ROOT)} with {manifest['count']} artworks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
