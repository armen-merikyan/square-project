#!/usr/bin/env python3

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ART_DIR = PROJECT_ROOT / "art"
ARTWORK_PAGE_DIR = PROJECT_ROOT / "artwork"
MANIFEST_PATH = ART_DIR / "manifest.json"
HOMEPAGE_ARTWORK_IDS_PATH = ART_DIR / "homepage-artwork-ids.json"
SITEMAP_PATH = PROJECT_ROOT / "sitemap.xml"
DEFAULT_SITE_URL = "https://mysquareart.com"
CHUNK_DIR_NAME = "manifest-chunks"
CATEGORY_DIR_NAME = "category-chunks"
CHUNK_SIZE = 500
CATEGORY_SIZE = 200
REASONING_PREVIEW_LENGTH = 360
COLOR_SIMILARITY_THRESHOLDS = list(range(0, 97, 8))
COLOR_FILTER_RENDER_LIMIT = 600
BASE_KEYWORDS = [
    "Square Project",
    "digital square art",
    "8x8 pixel art",
    "pixel square",
    "generative art",
    "abstract pixel art",
    "collectible digital art",
]


def site_url() -> str:
    cname_path = PROJECT_ROOT / "CNAME"

    if not cname_path.exists():
        return DEFAULT_SITE_URL

    hostname = cname_path.read_text(encoding="utf-8").strip().splitlines()[0].strip()
    return f"https://{hostname}" if hostname else DEFAULT_SITE_URL


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


def text_preview(value: Any, max_length: int) -> str:
    text = " ".join(str(value or "").split())

    if len(text) <= max_length:
        return text

    return text[:max_length].rsplit(" ", 1)[0].rstrip(".,;:") + "."


def keyword_values(record: dict[str, Any], colors: list[str]) -> list[str]:
    seed_terms = [
        part.strip().replace("_", " ")
        for part in str(record.get("seed", "")).replace(";", "|").split("|")
        if part.strip()
    ]
    values = [
        *BASE_KEYWORDS,
        str(record.get("title", "")).strip(),
        *seed_terms[:12],
        *colors[:10],
    ]
    keywords: list[str] = []
    seen: set[str] = set()

    for value in values:
        normalized = " ".join(str(value or "").split())
        key = normalized.casefold()

        if normalized and key not in seen:
            seen.add(key)
            keywords.append(normalized)

    return keywords


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
    title = str(record.get("title", "") or "Untitled square")
    gallery_record_data = {
        "id": artwork_id,
        "title": title,
        "seed": record.get("seed", ""),
        "reasoning": reasoning[:REASONING_PREVIEW_LENGTH],
        "description": artwork_description(record, colors),
        "keywords": keyword_values(record, colors),
        "pagePath": f"artwork/{artwork_id}/",
        "size": record.get("size", {"width": 8, "height": 8}),
        "colors": colors,
    }
    gallery_record_data["searchText"] = record_search_text(gallery_record_data, colors)

    return gallery_record_data


def artwork_description(record: dict[str, Any], colors: list[str]) -> str:
    title = str(record.get("title", "") or "Untitled square")
    reasoning = text_preview(record.get("reasoning", ""), 128)

    if reasoning:
        return text_preview(f"{title} is an 8 by 8 Square Project artwork. {reasoning}", 158)

    color_text = ", ".join(colors[:5])
    return text_preview(f"{title} is an 8 by 8 Square Project pixel artwork with colors {color_text}.", 158)


def artwork_json_ld(record: dict[str, Any], colors: list[str], base_url: str) -> str:
    artwork_id = str(record.get("id", ""))
    width = record.get("size", {}).get("width", 8)
    height = record.get("size", {}).get("height", 8)
    data = {
        "@context": "https://schema.org",
        "@type": "VisualArtwork",
        "name": str(record.get("title", "") or "Untitled square"),
        "description": artwork_description(record, colors),
        "artform": "Digital pixel art",
        "artMedium": "SVG and structured JSON",
        "creator": {
            "@type": "Organization",
            "name": "Athena Live LLC",
            "url": "https://athena.live",
        },
        "url": f"{base_url}/artwork/{artwork_id}/",
        "image": f"{base_url}/art/{artwork_id}.svg",
        "identifier": artwork_id,
        "keywords": keyword_values(record, colors),
        "width": width,
        "height": height,
        "encoding": [
            {
                "@type": "MediaObject",
                "contentUrl": f"{base_url}/art/{artwork_id}.svg",
                "encodingFormat": "image/svg+xml",
            },
            {
                "@type": "MediaObject",
                "contentUrl": f"{base_url}/art/{artwork_id}.json",
                "encodingFormat": "application/json",
            },
        ],
    }
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def render_artwork_page(record: dict[str, Any], colors: list[str], base_url: str) -> str:
    artwork_id = str(record.get("id", ""))
    title = str(record.get("title", "") or "Untitled square")
    description = artwork_description(record, colors)
    keywords = ", ".join(keyword_values(record, colors))
    canonical_url = f"{base_url}/artwork/{artwork_id}/"
    image_url = f"{base_url}/art/{artwork_id}.svg"
    width = record.get("size", {}).get("width", 8)
    height = record.get("size", {}).get("height", 8)
    cells = len(record.get("pixels") or []) or width * height
    swatches = "\n".join(
        f'              <span style="background:{escape(color, quote=True)}" title="{escape(color, quote=True)}" aria-label="{escape(color, quote=True)}"></span>'
        for color in colors
    )

    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{escape(title)} | Square Project Artwork</title>
    <meta name="description" content="{escape(description, quote=True)}">
    <meta name="keywords" content="{escape(keywords, quote=True)}">
    <meta name="author" content="Athena Live LLC">
    <link rel="canonical" href="{escape(canonical_url, quote=True)}">
    <meta property="og:site_name" content="Square Project">
    <meta property="og:type" content="article">
    <meta property="og:title" content="{escape(title, quote=True)} | Square Project">
    <meta property="og:description" content="{escape(description, quote=True)}">
    <meta property="og:url" content="{escape(canonical_url, quote=True)}">
    <meta property="og:image" content="{escape(image_url, quote=True)}">
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="{escape(title, quote=True)} | Square Project">
    <meta name="twitter:description" content="{escape(description, quote=True)}">
    <meta name="twitter:image" content="{escape(image_url, quote=True)}">
    <script type="application/ld+json">{artwork_json_ld(record, colors, base_url)}</script>
    <link rel="stylesheet" href="../../styles.css?v=20260601-art-pages">
  </head>
  <body>
    <header class="site-header">
      <a class="brand" href="../../index.html" aria-label="Square Project home">
        <span class="brand-mark" aria-hidden="true"></span>
        <span>Square Project</span>
      </a>
      <button
        class="menu-toggle"
        type="button"
        aria-label="Open navigation menu"
        aria-controls="primaryNavigation"
        aria-expanded="false"
      >
        <span aria-hidden="true"></span>
        <span aria-hidden="true"></span>
        <span aria-hidden="true"></span>
      </button>
      <nav id="primaryNavigation" aria-label="Primary navigation">
        <a href="../../gallery.html">Gallery</a>
        <a href="../../index.html#process">Process</a>
        <a href="../../index.html#data">Pixel Data</a>
        <a href="../../index.html#identity">Identity</a>
        <a href="../../terms.html">Terms</a>
        <a href="../../privacy.html">Privacy</a>
      </nav>
    </header>

    <main>
      <article class="artwork-page">
        <div class="artwork-page-preview">
          <img src="../../art/{escape(artwork_id, quote=True)}.svg" alt="{escape(title, quote=True)} artwork" decoding="async">
        </div>

        <div class="artwork-page-content">
          <p class="eyebrow">Square Project artwork</p>
          <h1>{escape(title)}</h1>
          <p class="artwork-page-seed">{escape(str(record.get("seed", "") or "No seed recorded"))}</p>

          <dl class="inspector-metrics">
            <div><dt>Grid</dt><dd>{escape(str(width))} x {escape(str(height))}</dd></div>
            <div><dt>Cells</dt><dd>{escape(str(cells))}</dd></div>
            <div><dt>Colors</dt><dd>{escape(str(len(colors)))}</dd></div>
            <div><dt>Record</dt><dd>{escape(artwork_id[:8])}</dd></div>
          </dl>

          <h2>Artist Statement</h2>
          <p>{escape(str(record.get("reasoning", "") or "No reasoning recorded."))}</p>

          <h2>Palette</h2>
          <div class="color-swatches">
{swatches}
          </div>

          <div class="artwork-page-actions">
            <a class="button primary" href="../../gallery.html?art={escape(artwork_id, quote=True)}">Open in gallery</a>
            <a class="button secondary" href="../../art/{escape(artwork_id, quote=True)}.json">View JSON</a>
            <a class="button secondary" href="../../art/{escape(artwork_id, quote=True)}.svg">View SVG</a>
          </div>
        </div>
      </article>
    </main>

    <footer>
      <p>
        Copyright © 2026
        <a href="https://athena.live" target="_blank" rel="noopener noreferrer">Athena Live LLC</a>.
        Digital squares, pixel worlds, and collectible 8 by 8 art.
      </p>
      <nav aria-label="Legal links">
        <a href="../../terms.html">Terms of Service</a>
        <a href="../../privacy.html">Privacy Policy</a>
      </nav>
    </footer>

    <script src="../../navigation.js?v=20260601"></script>
  </body>
</html>
"""


def build_artwork_pages(records: list[dict[str, Any]], art_dir: Path, page_dir: Path = ARTWORK_PAGE_DIR) -> list[str]:
    if page_dir.exists():
        shutil.rmtree(page_dir)

    page_dir.mkdir(parents=True, exist_ok=True)
    base_url = site_url().rstrip("/")
    urls: list[str] = []

    for record in records:
        artwork_id = str(record.get("id", ""))
        source = json.loads((art_dir / f"{artwork_id}.json").read_text(encoding="utf-8"))
        pixels = source.get("pixels") if isinstance(source.get("pixels"), list) else []
        colors = unique_colors(pixels)
        target_dir = page_dir / artwork_id
        target_dir.mkdir(parents=True, exist_ok=True)
        target_dir.joinpath("index.html").write_text(render_artwork_page(source, colors, base_url), encoding="utf-8")
        urls.append(f"{base_url}/artwork/{artwork_id}/")

    return urls


def write_sitemap(artwork_urls: list[str], base_url: str) -> None:
    today = datetime.now(timezone.utc).date().isoformat()
    static_urls = [
        f"{base_url}/",
        f"{base_url}/gallery.html",
        f"{base_url}/terms.html",
        f"{base_url}/privacy.html",
    ]
    url_entries = "\n".join(
        f"  <url><loc>{escape(url)}</loc><lastmod>{today}</lastmod></url>"
        for url in [*static_urls, *artwork_urls]
    )
    SITEMAP_PATH.write_text(
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{url_entries}\n"
        f"</urlset>\n",
        encoding="utf-8",
    )


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
    artwork_urls = build_artwork_pages(all_records, art_dir)
    write_sitemap(artwork_urls, site_url().rstrip("/"))
    return manifest


def main() -> int:
    manifest = build_gallery_manifest()
    print(f"Wrote {MANIFEST_PATH.relative_to(PROJECT_ROOT)} with {manifest['count']} artworks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
