#!/usr/bin/env python3
"""Publish or create Stripe products and payment links for Square Project art."""

from __future__ import annotations

import json
import os
import ssl
import tempfile
import time
import urllib.parse
import urllib.request
from base64 import b64encode
from concurrent.futures import ThreadPoolExecutor, as_completed
from html import escape
from pathlib import Path
from threading import Lock
from urllib.error import HTTPError, URLError

try:
    import certifi
except ImportError:  # pragma: no cover - script still works on systems with a valid CA store.
    certifi = None


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
PAYMENT_LINKS_PATH = ROOT / "payment-links.js"
STRIPE_SYNC_CACHE_PATH = ROOT / ".stripe-sync-cache.json"
ART_DIR = ROOT / "art"
STRIPE_PREVIEW_DIR = ROOT / "stripe-previews"
MANIFEST_PATH = ART_DIR / "manifest.json"
PAYMENT_LINKS_JS_PREFIX = "window.SQUARE_PROJECT_PAYMENT_LINKS = "
STRIPE_CONTEXT = ssl.create_default_context(cafile=certifi.where()) if certifi else None
STRIPE_SYNC_CACHE_VERSION = 1
DEFAULT_SITE_URL = "https://mysquareart.com"
FRAME_PREVIEW_STAGE_SIZE = 1500
FRAME_PREVIEW_ART_X = FRAME_PREVIEW_STAGE_SIZE / 6
FRAME_PREVIEW_ART_Y = FRAME_PREVIEW_STAGE_SIZE / 6
FRAME_PREVIEW_ART_SIZE = FRAME_PREVIEW_STAGE_SIZE * (2 / 3)
FRAME_COLORS = {
    "black": "Black",
    "white": "White",
    "natural": "Natural",
    "brown": "Brown",
    "gold": "Gold",
}
FRAME_DATA_URI_CACHE: dict[str, str] = {}
VARIANTS = {
    "print": {
        "nickname": "Square Project 8x8 Art Print",
        "label": "Art print",
        "amount": 2400,
        "lookup_key_template": "square_project_art_{art_id}_print",
        "env_key": "STRIPE_PRINT_PRICE_ID",
        "payment_link_env_key": "STRIPE_PRINT_PAYMENT_LINK",
        "payment_link_lookup_key_template": "square_project_art_{art_id}_print_payment_link",
        "metadata": {
            "variant": "print",
            "image_area": "8x8",
            "frame_size": "none",
        },
    },
    "framed": {
        "nickname": "Square Project 12x12 Framed Print",
        "label": "12x12 framed print",
        "amount": 3900,
        "lookup_key_template": "square_project_art_{art_id}_framed_{frame_color}",
        "env_key": "STRIPE_FRAMED_PRICE_ID",
        "payment_link_env_key": "STRIPE_FRAMED_PAYMENT_LINK",
        "payment_link_lookup_key_template": "square_project_art_{art_id}_framed_{frame_color}_payment_link",
        "metadata": {
            "variant": "framed",
            "image_area": "8x8",
            "frame_size": "12x12",
            "frame_colors": ",".join(FRAME_COLORS),
        },
    },
}


def clean_env_value(value: str) -> str:
    return value.strip().strip("\"'")


def is_real_stripe_id(value: str, prefix: str) -> bool:
    return value.startswith(prefix) and "_your" not in value and "your-" not in value


def is_real_payment_link(value: str) -> bool:
    parsed = urllib.parse.urlparse(value)
    return (
        parsed.scheme == "https"
        and parsed.netloc.startswith("buy.")
        and bool(parsed.path.strip("/"))
        and "your-" not in value
    )


def load_env() -> None:
    if not ENV_PATH.is_file():
        return

    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()

        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue

        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), clean_env_value(value))


def update_env(updates: dict[str, str]) -> None:
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.is_file() else []
    seen = set()
    next_lines = []

    for line in lines:
        if "=" not in line or line.lstrip().startswith("#"):
            next_lines.append(line)
            continue

        key = line.split("=", 1)[0].strip()

        if key in updates:
            next_lines.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            next_lines.append(line)

    for key, value in updates.items():
        if key not in seen:
            next_lines.append(f"{key}={value}")

    ENV_PATH.write_text("\n".join(next_lines) + "\n", encoding="utf-8")


def site_url() -> str:
    return clean_env_value(os.environ.get("STRIPE_SITE_URL", DEFAULT_SITE_URL)).rstrip("/")


def enabled_env_flag(key: str) -> bool:
    return clean_env_value(os.environ.get(key, "")).lower() in {"1", "true", "yes", "on"}


def update_payment_links_js(payment_config: dict) -> None:
    payload = json.dumps(payment_config, indent=2, sort_keys=True)
    PAYMENT_LINKS_PATH.write_text(
        f"{PAYMENT_LINKS_JS_PREFIX}{payload};\n",
        encoding="utf-8",
    )


def load_stripe_sync_cache() -> dict:
    if not STRIPE_SYNC_CACHE_PATH.is_file():
        return {"version": STRIPE_SYNC_CACHE_VERSION, "artworks": {}}

    try:
        payload = json.loads(STRIPE_SYNC_CACHE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"version": STRIPE_SYNC_CACHE_VERSION, "artworks": {}}

    if not isinstance(payload, dict) or payload.get("version") != STRIPE_SYNC_CACHE_VERSION:
        return {"version": STRIPE_SYNC_CACHE_VERSION, "artworks": {}}

    artworks = payload.get("artworks")
    if not isinstance(artworks, dict):
        payload["artworks"] = {}

    return payload


def save_stripe_sync_cache(cache: dict) -> None:
    cache["version"] = STRIPE_SYNC_CACHE_VERSION
    cache.setdefault("artworks", {})

    payload = json.dumps(cache, indent=2, sort_keys=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=ROOT, delete=False) as temp_file:
        temp_file.write(payload)
        temp_file.write("\n")
        temp_path = Path(temp_file.name)

    temp_path.replace(STRIPE_SYNC_CACHE_PATH)


def file_signature(path: Path) -> dict[str, int | str]:
    stat = path.stat()
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


def stripe_sync_signature() -> dict:
    variant_signature = {}

    for variant, config in VARIANTS.items():
        variant_signature[variant] = {
            "amount": config["amount"],
            "lookup_key_template": config["lookup_key_template"],
            "payment_link_lookup_key_template": config["payment_link_lookup_key_template"],
            "metadata": config["metadata"],
        }

    return {
        "site_url": site_url(),
        "frame_colors": FRAME_COLORS,
        "variants": variant_signature,
    }


def artwork_sync_signature(art_id: str, sync_signature: dict) -> dict | None:
    json_path = ART_DIR / f"{art_id}.json"
    svg_path = ART_DIR / f"{art_id}.svg"

    if not json_path.is_file() or not svg_path.is_file():
        return None

    return {
        "sync": sync_signature,
        "json": file_signature(json_path),
        "svg": file_signature(svg_path),
    }


def valid_cached_links(links: object) -> bool:
    if not isinstance(links, dict) or not is_real_payment_link(str(links.get("print", ""))):
        return False

    framed = links.get("framed")
    if not isinstance(framed, dict):
        return False

    return all(is_real_payment_link(str(framed.get(frame_color, ""))) for frame_color in FRAME_COLORS)


def changed_artwork_ids(ids: list[str], cache: dict, sync_signature: dict) -> tuple[list[str], dict[str, dict[str, str]], dict[str, dict]]:
    cached_artworks = cache.get("artworks") if isinstance(cache.get("artworks"), dict) else {}
    changed_ids: list[str] = []
    cached_links: dict[str, dict[str, str]] = {}
    signatures: dict[str, dict] = {}

    for art_id in ids:
        signature = artwork_sync_signature(art_id, sync_signature)

        if signature is None:
            changed_ids.append(art_id)
            continue

        signatures[art_id] = signature
        entry = cached_artworks.get(art_id) if isinstance(cached_artworks, dict) else None
        links = entry.get("links") if isinstance(entry, dict) else None

        if isinstance(entry, dict) and entry.get("signature") == signature and valid_cached_links(links):
            cached_links[art_id] = links
        else:
            changed_ids.append(art_id)

    return changed_ids, cached_links, signatures


def existing_payment_links_payload() -> dict:
    if not PAYMENT_LINKS_PATH.is_file():
        return {}

    text = PAYMENT_LINKS_PATH.read_text(encoding="utf-8").strip()
    if not text.startswith(PAYMENT_LINKS_JS_PREFIX):
        return {}

    payload_text = text[len(PAYMENT_LINKS_JS_PREFIX):].strip()
    if payload_text.endswith(";"):
        payload_text = payload_text[:-1].strip()

    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError:
        return {}

    return payload if isinstance(payload, dict) else {}


def merged_payment_links_payload(
    artwork_links: dict[str, dict[str, str]],
    legacy_links: dict[str, str] | None = None,
) -> dict:
    existing_payload = existing_payment_links_payload()
    existing_artworks = existing_payload.get("artworks")
    merged_artworks = dict(existing_artworks) if isinstance(existing_artworks, dict) else {}
    merged_artworks.update(artwork_links)
    return payment_links_payload(merged_artworks, legacy_links)


def stripe_post(path: str, fields: dict[str, str]) -> dict:
    secret_key = os.environ.get("STRIPE_SECRET_KEY", "").strip()

    if not secret_key:
        raise SystemExit("Set STRIPE_SECRET_KEY in .env before running this script.")

    for attempt in range(5):
        request = urllib.request.Request(
            f"https://api.stripe.com/v1/{path.lstrip('/')}",
            data=urllib.parse.urlencode(fields).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {secret_key}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=20, context=STRIPE_CONTEXT) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            try:
                payload = json.loads(error.read().decode("utf-8"))
                message = payload.get("error", {}).get("message")
            except (json.JSONDecodeError, UnicodeDecodeError):
                message = None

            if error.code in {409, 429, 500, 502, 503, 504} and attempt < 4:
                time.sleep(2 ** attempt)
                continue

            raise SystemExit(message or f"Stripe returned HTTP {error.code}.") from error
        except URLError:
            if attempt < 4:
                time.sleep(2 ** attempt)
                continue
            raise

    raise SystemExit("Stripe request failed after retries.")


def stripe_get(path: str, fields: dict[str, str]) -> dict:
    secret_key = os.environ.get("STRIPE_SECRET_KEY", "").strip()

    if not secret_key:
        raise SystemExit("Set STRIPE_SECRET_KEY in .env before running this script.")

    for attempt in range(5):
        url = f"https://api.stripe.com/v1/{path.lstrip('/')}?{urllib.parse.urlencode(fields)}"
        request = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {secret_key}"},
            method="GET",
        )

        try:
            with urllib.request.urlopen(request, timeout=20, context=STRIPE_CONTEXT) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            try:
                payload = json.loads(error.read().decode("utf-8"))
                message = payload.get("error", {}).get("message")
            except (json.JSONDecodeError, UnicodeDecodeError):
                message = None

            if error.code in {409, 429, 500, 502, 503, 504} and attempt < 4:
                time.sleep(2 ** attempt)
                continue

            raise SystemExit(message or f"Stripe returned HTTP {error.code}.") from error
        except URLError:
            if attempt < 4:
                time.sleep(2 ** attempt)
                continue
            raise

    raise SystemExit("Stripe request failed after retries.")


def find_price_by_lookup_key(lookup_key: str) -> dict | None:
    prices = stripe_get("prices", {
        "active": "true",
        "lookup_keys[]": lookup_key,
        "limit": "1",
    })
    data = prices.get("data", [])
    return data[0] if data else None


def iter_prices():
    starting_after = ""

    while True:
        fields = {
            "active": "true",
            "limit": "100",
        }

        if starting_after:
            fields["starting_after"] = starting_after

        prices = stripe_get("prices", fields)
        data = prices.get("data", [])

        yield from data

        if not prices.get("has_more") or not data:
            break

        starting_after = data[-1]["id"]


def prices_by_lookup_key() -> dict[str, dict]:
    prices = {}

    for price in iter_prices():
        lookup_key = price.get("lookup_key")

        if lookup_key:
            prices[lookup_key] = price

    return prices


def payment_links_by_lookup_key() -> dict[str, dict]:
    links = {}

    for payment_link in iter_payment_links():
        lookup_key = payment_link.get("metadata", {}).get("lookup_key")

        if lookup_key:
            links[lookup_key] = payment_link

    return links


def expected_price_lookup_keys(ids: list[str]) -> set[str]:
    keys: set[str] = set()

    for art_id in ids:
        for variant, config in VARIANTS.items():
            frame_colors = FRAME_COLORS.keys() if variant == "framed" else [None]

            for frame_color in frame_colors:
                keys.add(lookup_key(config, art_id, frame_color))

    return keys


def scoped_prices_by_lookup_key(ids: list[str]) -> dict[str, dict]:
    prices: dict[str, dict] = {}

    for key in sorted(expected_price_lookup_keys(ids)):
        price = find_price_by_lookup_key(key)

        if price:
            prices[key] = price

    return prices


def iter_payment_links():
    starting_after = ""

    while True:
        fields = {
            "active": "true",
            "limit": "100",
        }

        if starting_after:
            fields["starting_after"] = starting_after

        payment_links = stripe_get("payment_links", fields)
        data = payment_links.get("data", [])

        yield from data

        if not payment_links.get("has_more") or not data:
            break

        starting_after = data[-1]["id"]


def find_payment_link_by_url(url: str) -> dict | None:
    if not url:
        return None

    for payment_link in iter_payment_links():
        if payment_link.get("url") == url:
            return payment_link

    return None


def payment_link_price_id(payment_link_id: str) -> str:
    line_items = stripe_get(f"payment_links/{payment_link_id}/line_items", {"limit": "1"})
    data = line_items.get("data", [])

    if not data:
        return ""

    return data[0].get("price", {}).get("id", "")


def artwork_ids() -> list[str]:
    if MANIFEST_PATH.is_file():
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        ids = manifest if isinstance(manifest, list) else manifest.get("artworkIds", [])

        if isinstance(ids, list) and ids:
            return [str(artwork_id) for artwork_id in ids]

    json_ids = {path.stem for path in ART_DIR.glob("*.json") if path.name != MANIFEST_PATH.name}
    svg_ids = {path.stem for path in ART_DIR.glob("*.svg")}
    return sorted(json_ids & svg_ids)


def artwork_record(art_id: str) -> dict:
    record_path = ART_DIR / f"{art_id}.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    pixels = record.get("pixels") if isinstance(record.get("pixels"), list) else []
    colors = []
    seen_colors = set()

    for pixel in pixels:
        color = str(pixel.get("color", "")).strip().upper()

        if color and color not in seen_colors:
            seen_colors.add(color)
            colors.append(color)

    return {
        "id": art_id,
        "title": str(record.get("title") or f"Square Project {art_id[:8]}"),
        "seed": str(record.get("seed") or ""),
        "reasoning": str(record.get("reasoning") or ""),
        "pixels": pixels,
        "colors": colors,
        "image_url": f"{site_url()}/art/{art_id}.svg",
        "json_url": f"{site_url()}/art/{art_id}.json",
    }


def stripe_metadata_value(value: str) -> str:
    return str(value)[:500]


def metadata_fields(prefix: str, metadata: dict[str, str]) -> dict[str, str]:
    return {f"{prefix}[{key}]": stripe_metadata_value(value) for key, value in metadata.items()}


def framed_preview_path(art_id: str, frame_color: str) -> Path:
    return STRIPE_PREVIEW_DIR / f"{art_id}_{frame_color}.svg"


def framed_preview_url(art_id: str, frame_color: str) -> str:
    return f"{site_url()}/stripe-previews/{art_id}_{frame_color}.svg"


def frame_data_uri(frame_color: str) -> str:
    cached_uri = FRAME_DATA_URI_CACHE.get(frame_color)

    if cached_uri:
        return cached_uri

    frame_path = ROOT / "frames" / f"{frame_color}.jpg"
    encoded_frame = b64encode(frame_path.read_bytes()).decode("ascii")
    uri = f"data:image/jpeg;base64,{encoded_frame}"
    FRAME_DATA_URI_CACHE[frame_color] = uri
    return uri


def write_framed_preview_svg(art: dict, frame_color: str) -> None:
    STRIPE_PREVIEW_DIR.mkdir(parents=True, exist_ok=True)

    stage_size = FRAME_PREVIEW_STAGE_SIZE
    art_x = FRAME_PREVIEW_ART_X
    art_y = FRAME_PREVIEW_ART_Y
    art_size = FRAME_PREVIEW_ART_SIZE
    cell_size = art_size / 8
    frame_uri = frame_data_uri(frame_color)
    rects = [
        f'<rect x="{art_x + int(pixel.get("x", 0)) * cell_size:g}" '
        f'y="{art_y + int(pixel.get("y", 0)) * cell_size:g}" '
        f'width="{cell_size:g}" height="{cell_size:g}" '
        f'fill="{escape(str(pixel.get("color", "#FFFFFF")))}" />'
        for pixel in art["pixels"]
        if isinstance(pixel, dict)
    ]
    title = escape(f'{art["title"]} in {FRAME_COLORS[frame_color]} frame')
    desc = escape(f'Square Project artwork previewed in a {FRAME_COLORS[frame_color].lower()} frame.')

    framed_preview_path(art["id"], frame_color).write_text(
        "\n".join([
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{stage_size}" height="{stage_size}" viewBox="0 0 {stage_size} {stage_size}" shape-rendering="crispEdges" role="img" aria-labelledby="title desc">',
            f'  <title id="title">{title}</title>',
            f'  <desc id="desc">{desc}</desc>',
            f'  <rect x="0" y="0" width="{stage_size}" height="{stage_size}" fill="#FFFFFF" />',
            f'  <image href="{escape(frame_uri)}" x="0" y="0" width="{stage_size}" height="{stage_size}" preserveAspectRatio="xMidYMid meet" />',
            f'  <rect x="{art_x:g}" y="{art_y:g}" width="{art_size:g}" height="{art_size:g}" fill="#FFFFFF" />',
            *[f"  {rect}" for rect in rects],
            f'  <rect x="{art_x:g}" y="{art_y:g}" width="{art_size:g}" height="{art_size:g}" fill="none" stroke="#151515" stroke-opacity="0.16" stroke-width="2" />',
            "</svg>",
            "",
        ]),
        encoding="utf-8",
    )


def image_url_for_variant(art: dict, variant: str | None = None, frame_color: str | None = None) -> str:
    if variant == "framed" and frame_color:
        return framed_preview_url(art["id"], frame_color)

    return art["image_url"]


def art_metadata(art: dict, variant: str | None = None, frame_color: str | None = None) -> dict[str, str]:
    image_url = image_url_for_variant(art, variant, frame_color)
    metadata = {
        "metadata[app]": stripe_metadata_value("square_project"),
        "metadata[kind]": stripe_metadata_value("artwork"),
        "metadata[site]": stripe_metadata_value(site_url()),
        "metadata[art_id]": stripe_metadata_value(art["id"]),
        "metadata[art_title]": stripe_metadata_value(art["title"]),
        "metadata[art_seed]": stripe_metadata_value(art["seed"]),
        "metadata[art_colors]": stripe_metadata_value(",".join(art["colors"])),
        "metadata[art_image_url]": stripe_metadata_value(image_url),
        "metadata[art_json_url]": stripe_metadata_value(art["json_url"]),
    }

    if variant:
        metadata["metadata[variant]"] = stripe_metadata_value(variant)

    if frame_color:
        metadata["metadata[frame_color]"] = stripe_metadata_value(frame_color)
        metadata["metadata[frame_color_label]"] = stripe_metadata_value(FRAME_COLORS.get(frame_color, frame_color))

    return metadata


def product_fields(art: dict, variant: str | None = None, frame_color: str | None = None) -> dict[str, str]:
    description = art["reasoning"][:480] or f"Square Project artwork {art['id']}."
    name = art["title"][:250]

    if variant == "framed" and frame_color:
        name = f'{art["title"]} - {FRAME_COLORS[frame_color]} frame'[:250]

    return {
        "name": name,
        "description": description,
        "images[0]": image_url_for_variant(art, variant, frame_color),
        **art_metadata(art, variant, frame_color),
    }


def update_product_metadata(product_id: str, art: dict, variant: str | None = None, frame_color: str | None = None) -> None:
    stripe_post(f"products/{product_id}", product_fields(art, variant, frame_color))


def payment_link_metadata_fields(
    art: dict,
    variant: str,
    config: dict,
    lookup_key: str,
    frame_color: str | None = None,
) -> dict[str, str]:
    fields = {
        "metadata[app]": stripe_metadata_value("square_project"),
        "metadata[kind]": stripe_metadata_value("artwork_order"),
        "metadata[art_id]": stripe_metadata_value(art["id"]),
        "metadata[art_title]": stripe_metadata_value(art["title"]),
        "metadata[variant]": stripe_metadata_value(variant),
        "metadata[lookup_key]": stripe_metadata_value(lookup_key),
        "metadata[order_reference_format]": stripe_metadata_value("art_<art_id>_variant_<variant>_frame_<frame_color>"),
        "metadata[custom_field_mode]": stripe_metadata_value("none"),
    }

    if frame_color:
        fields["metadata[frame_color]"] = stripe_metadata_value(frame_color)
        fields["metadata[frame_color_label]"] = stripe_metadata_value(FRAME_COLORS.get(frame_color, frame_color))

    for key, value in config["metadata"].items():
        fields[f"metadata[{key}]"] = stripe_metadata_value(value)

    return fields


def update_payment_link_metadata(
    payment_link_id: str,
    art: dict,
    variant: str,
    config: dict,
    lookup_key: str,
    frame_color: str | None = None,
) -> None:
    stripe_post(
        f"payment_links/{payment_link_id}",
        payment_link_metadata_fields(art, variant, config, lookup_key, frame_color),
    )


def legacy_payment_links_from_env() -> dict[str, str]:
    return {
        variant: os.environ.get(config["payment_link_env_key"], "").strip()
        for variant, config in VARIANTS.items()
    }


def real_legacy_payment_links(payment_links: dict[str, str]) -> dict[str, str]:
    return {
        variant: url
        for variant, url in payment_links.items()
        if is_real_payment_link(url)
    }


def payment_links_payload(artwork_links: dict[str, dict[str, str]], legacy_links: dict[str, str] | None = None) -> dict:
    payload = {
        "artworks": artwork_links,
        "frameColors": [
            {"value": value, "label": label}
            for value, label in FRAME_COLORS.items()
        ],
        "variants": {
            variant: {
                "label": config["label"],
                "amount": config["amount"],
                "currency": "usd",
            }
            for variant, config in VARIANTS.items()
        },
    }

    for variant, url in (legacy_links or {}).items():
        if url:
            payload[variant] = url

    return payload


def lookup_key(config: dict, art_id: str, frame_color: str | None = None) -> str:
    return config["lookup_key_template"].format(
        art_id=art_id,
        frame_color=frame_color or "none",
    )


def payment_link_lookup_key(config: dict, art_id: str, frame_color: str | None = None) -> str:
    return config["payment_link_lookup_key_template"].format(
        art_id=art_id,
        frame_color=frame_color or "none",
    )


def limited_artwork_ids() -> list[str]:
    ids = artwork_ids()
    selected_ids = [
        value.strip()
        for value in os.environ.get("STRIPE_ARTWORK_IDS", "").replace("\n", ",").split(",")
        if value.strip()
    ]

    if selected_ids:
        selected = set(selected_ids)
        ids = [art_id for art_id in ids if art_id in selected]

    limit = int(os.environ.get("STRIPE_ARTWORK_LIMIT", "0") or "0")

    if limit > 0:
        ids = ids[:limit]

    return ids


def write_framed_previews(ids: list[str]) -> None:
    for art_id in ids:
        art = artwork_record(art_id)

        for frame_color in FRAME_COLORS:
            write_framed_preview_svg(art, frame_color)


def main() -> None:
    load_env()
    env_payment_links = legacy_payment_links_from_env()

    ids = limited_artwork_ids()

    if enabled_env_flag("STRIPE_PREVIEWS_ONLY"):
        write_framed_previews(ids)
        print(f"Wrote framed Stripe previews for {len(ids)} artworks to {STRIPE_PREVIEW_DIR}.")
        return

    secret_key = os.environ.get("STRIPE_SECRET_KEY", "").strip()

    if all(is_real_payment_link(url) for url in env_payment_links.values()) and not secret_key:
        update_payment_links_js(merged_payment_links_payload({}, env_payment_links))
        print(f"Updated {PAYMENT_LINKS_PATH} from existing Stripe Payment Links in {ENV_PATH}.")
        return

    if not secret_key and any(env_payment_links.values()) and not all(
        is_real_payment_link(url) for url in env_payment_links.values()
    ):
        invalid_keys = [
            config["payment_link_env_key"]
            for variant, config in VARIANTS.items()
            if not is_real_payment_link(env_payment_links[variant])
        ]
        raise SystemExit(
            "Fix these Stripe Payment Link values in .env before publishing: "
            + ", ".join(invalid_keys)
        )

    if not secret_key:
        raise SystemExit(
            "For legacy static-site links, add STRIPE_PRINT_PAYMENT_LINK and "
            "STRIPE_FRAMED_PAYMENT_LINK Stripe Payment Link URLs to .env, then rerun this script. "
            "Set STRIPE_SECRET_KEY to create one Stripe product and payment links per artwork."
        )

    sync_signature = stripe_sync_signature()
    sync_cache = load_stripe_sync_cache()
    changed_ids, cached_artwork_links, art_signatures = changed_artwork_ids(ids, sync_cache, sync_signature)

    print(
        f"Preparing Stripe products for {len(changed_ids)} changed artworks "
        f"({len(cached_artwork_links)} cached, {len(ids)} selected).",
        flush=True,
    )

    if not changed_ids:
        update_payment_links_js(
            merged_payment_links_payload(cached_artwork_links, real_legacy_payment_links(env_payment_links))
        )
        save_stripe_sync_cache(sync_cache)
        print(f"No Stripe changes needed. Updated {PAYMENT_LINKS_PATH} from {STRIPE_SYNC_CACHE_PATH}.")
        return

    if enabled_env_flag("STRIPE_PRICE_LOOKUP_ON_MISS"):
        prices_by_lookup = {}
    elif enabled_env_flag("STRIPE_SCOPED_PRICE_LOOKUP"):
        prices_by_lookup = scoped_prices_by_lookup_key(changed_ids)
    else:
        prices_by_lookup = prices_by_lookup_key()

    links_by_lookup_key = {} if enabled_env_flag("STRIPE_SKIP_PAYMENT_LINK_PRELOAD") else payment_links_by_lookup_key()
    artwork_links: dict[str, dict[str, str]] = dict(cached_artwork_links)
    cache_lock = Lock()
    worker_count = max(1, int(os.environ.get("STRIPE_WORKERS", "6") or "6"))

    def process_artwork(art_id: str) -> tuple[str, dict[str, str], str]:
        art = artwork_record(art_id)
        links: dict[str, str] = {}
        last_product_id = ""

        for variant, config in VARIANTS.items():
            frame_colors = FRAME_COLORS.keys() if variant == "framed" else [None]

            for frame_color in frame_colors:
                if frame_color:
                    write_framed_preview_svg(art, frame_color)

                price_lookup_key = lookup_key(config, art_id, frame_color)
                with cache_lock:
                    price = prices_by_lookup.get(price_lookup_key)

                if not price and enabled_env_flag("STRIPE_PRICE_LOOKUP_ON_MISS"):
                    price = find_price_by_lookup_key(price_lookup_key)

                    if price:
                        with cache_lock:
                            prices_by_lookup[price_lookup_key] = price

                product_id = price["product"] if price else ""

                if product_id:
                    update_product_metadata(product_id, art, variant, frame_color)
                else:
                    product = stripe_post("products", product_fields(art, variant, frame_color))
                    product_id = product["id"]
                    last_product_id = product_id

                if not price:
                    price = stripe_post("prices", {
                        "currency": "usd",
                        "unit_amount": str(config["amount"]),
                        "product": product_id,
                        "nickname": config["nickname"],
                        "lookup_key": price_lookup_key,
                        **art_metadata(art, variant, frame_color),
                        **metadata_fields("metadata", config["metadata"]),
                    })
                    with cache_lock:
                        prices_by_lookup[price_lookup_key] = price

                link_lookup_key = payment_link_lookup_key(config, art_id, frame_color)
                with cache_lock:
                    payment_link = links_by_lookup_key.get(link_lookup_key)

                if payment_link:
                    update_payment_link_metadata(payment_link["id"], art, variant, config, link_lookup_key, frame_color)
                else:
                    fields = {
                        "line_items[0][price]": price["id"],
                        "line_items[0][quantity]": "1",
                        "shipping_address_collection[allowed_countries][0]": "US",
                        "billing_address_collection": "auto",
                        **payment_link_metadata_fields(art, variant, config, link_lookup_key, frame_color),
                    }

                    payment_link = stripe_post("payment_links", fields)
                    with cache_lock:
                        links_by_lookup_key[link_lookup_key] = payment_link

                if frame_color:
                    links.setdefault(variant, {})[frame_color] = payment_link["url"]
                else:
                    links[variant] = payment_link["url"]

        return art_id, links, last_product_id or "updated"

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {executor.submit(process_artwork, art_id): art_id for art_id in changed_ids}

        for index, future in enumerate(as_completed(futures), start=1):
            art_id, links, result = future.result()
            with cache_lock:
                artwork_links[art_id] = links
                sync_cache.setdefault("artworks", {})[art_id] = {
                    "signature": art_signatures.get(art_id) or artwork_sync_signature(art_id, sync_signature),
                    "links": links,
                    "synced_at": int(time.time()),
                }
            print(f"[{index}/{len(changed_ids)}] {art_id} -> {result}", flush=True)

    update_payment_links_js(merged_payment_links_payload(artwork_links, real_legacy_payment_links(env_payment_links)))
    save_stripe_sync_cache(sync_cache)
    print(f"\nUpdated {PAYMENT_LINKS_PATH} with {len(artwork_links)} artwork link sets.")


if __name__ == "__main__":
    main()
