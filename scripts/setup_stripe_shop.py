#!/usr/bin/env python3
"""Publish or create Stripe products and payment links for Square Project art."""

from __future__ import annotations

import json
import os
import ssl
import urllib.parse
import urllib.request
from pathlib import Path
from urllib.error import HTTPError

try:
    import certifi
except ImportError:  # pragma: no cover - script still works on systems with a valid CA store.
    certifi = None


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
PAYMENT_LINKS_PATH = ROOT / "payment-links.js"
ART_DIR = ROOT / "art"
MANIFEST_PATH = ART_DIR / "manifest.json"
STRIPE_CONTEXT = ssl.create_default_context(cafile=certifi.where()) if certifi else None
DEFAULT_SITE_URL = "https://mysquareart.com"
FRAME_COLORS = {
    "black": "Black",
    "white": "White",
    "natural": "Natural",
    "brown": "Brown",
    "gold": "Gold",
}
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
        "lookup_key_template": "square_project_art_{art_id}_framed",
        "env_key": "STRIPE_FRAMED_PRICE_ID",
        "payment_link_env_key": "STRIPE_FRAMED_PAYMENT_LINK",
        "payment_link_lookup_key_template": "square_project_art_{art_id}_framed_payment_link",
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


def update_payment_links_js(payment_config: dict) -> None:
    payload = json.dumps(payment_config, indent=2, sort_keys=True)
    PAYMENT_LINKS_PATH.write_text(
        f"window.SQUARE_PROJECT_PAYMENT_LINKS = {payload};\n",
        encoding="utf-8",
    )


def stripe_post(path: str, fields: dict[str, str]) -> dict:
    secret_key = os.environ.get("STRIPE_SECRET_KEY", "").strip()

    if not secret_key:
        raise SystemExit("Set STRIPE_SECRET_KEY in .env before running this script.")

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

        raise SystemExit(message or f"Stripe returned HTTP {error.code}.") from error


def stripe_get(path: str, fields: dict[str, str]) -> dict:
    secret_key = os.environ.get("STRIPE_SECRET_KEY", "").strip()

    if not secret_key:
        raise SystemExit("Set STRIPE_SECRET_KEY in .env before running this script.")

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

        raise SystemExit(message or f"Stripe returned HTTP {error.code}.") from error


def find_price_by_lookup_key(lookup_key: str) -> dict | None:
    prices = stripe_get("prices", {
        "active": "true",
        "lookup_keys[]": lookup_key,
        "limit": "1",
    })
    data = prices.get("data", [])
    return data[0] if data else None


def payment_links_by_lookup_key() -> dict[str, dict]:
    links = {}

    for payment_link in iter_payment_links():
        lookup_key = payment_link.get("metadata", {}).get("lookup_key")

        if lookup_key:
            links[lookup_key] = payment_link

    return links


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
        "colors": colors,
        "image_url": f"{site_url()}/art/{art_id}.svg",
        "json_url": f"{site_url()}/art/{art_id}.json",
    }


def stripe_metadata_value(value: str) -> str:
    return str(value)[:500]


def metadata_fields(prefix: str, metadata: dict[str, str]) -> dict[str, str]:
    return {f"{prefix}[{key}]": stripe_metadata_value(value) for key, value in metadata.items()}


def art_metadata(art: dict, variant: str | None = None) -> dict[str, str]:
    metadata = {
        "metadata[app]": stripe_metadata_value("square_project"),
        "metadata[kind]": stripe_metadata_value("artwork"),
        "metadata[site]": stripe_metadata_value(site_url()),
        "metadata[art_id]": stripe_metadata_value(art["id"]),
        "metadata[art_title]": stripe_metadata_value(art["title"]),
        "metadata[art_seed]": stripe_metadata_value(art["seed"]),
        "metadata[art_colors]": stripe_metadata_value(",".join(art["colors"])),
        "metadata[art_image_url]": stripe_metadata_value(art["image_url"]),
        "metadata[art_json_url]": stripe_metadata_value(art["json_url"]),
    }

    if variant:
        metadata["metadata[variant]"] = stripe_metadata_value(variant)

    return metadata


def product_fields(art: dict) -> dict[str, str]:
    description = art["reasoning"][:480] or f"Square Project artwork {art['id']}."
    return {
        "name": art["title"][:250],
        "description": description,
        "images[0]": art["image_url"],
        **art_metadata(art),
    }


def update_product_metadata(product_id: str, art: dict) -> None:
    stripe_post(f"products/{product_id}", product_fields(art))


def payment_link_metadata_fields(art: dict, variant: str, config: dict, lookup_key: str) -> dict[str, str]:
    fields = {
        "metadata[app]": stripe_metadata_value("square_project"),
        "metadata[kind]": stripe_metadata_value("artwork_order"),
        "metadata[art_id]": stripe_metadata_value(art["id"]),
        "metadata[art_title]": stripe_metadata_value(art["title"]),
        "metadata[variant]": stripe_metadata_value(variant),
        "metadata[lookup_key]": stripe_metadata_value(lookup_key),
        "metadata[order_reference_format]": stripe_metadata_value("art_<art_id>_variant_<variant>_frame_<frame_color>"),
        "metadata[custom_field_mode]": stripe_metadata_value("frame_color" if variant == "framed" else "art_only"),
    }

    for key, value in config["metadata"].items():
        fields[f"metadata[{key}]"] = stripe_metadata_value(value)

    return fields


def frame_color_custom_field() -> dict[str, str]:
    fields = {
        "custom_fields[0][key]": "frame_color",
        "custom_fields[0][label][type]": "custom",
        "custom_fields[0][label][custom]": "Frame color",
        "custom_fields[0][type]": "dropdown",
    }

    for index, (value, label) in enumerate(FRAME_COLORS.items()):
        fields[f"custom_fields[0][dropdown][options][{index}][label]"] = label
        fields[f"custom_fields[0][dropdown][options][{index}][value]"] = value

    return fields


def update_payment_link_metadata(payment_link_id: str, art: dict, variant: str, config: dict, lookup_key: str) -> None:
    stripe_post(f"payment_links/{payment_link_id}", payment_link_metadata_fields(art, variant, config, lookup_key))


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


def lookup_key(config: dict, art_id: str) -> str:
    return config["lookup_key_template"].format(art_id=art_id)


def payment_link_lookup_key(config: dict, art_id: str) -> str:
    return config["payment_link_lookup_key_template"].format(art_id=art_id)


def main() -> None:
    load_env()
    env_payment_links = legacy_payment_links_from_env()

    secret_key = os.environ.get("STRIPE_SECRET_KEY", "").strip()

    if all(is_real_payment_link(url) for url in env_payment_links.values()) and not secret_key:
        update_payment_links_js(env_payment_links)
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

    ids = artwork_ids()
    limit = int(os.environ.get("STRIPE_ARTWORK_LIMIT", "0") or "0")

    if limit > 0:
        ids = ids[:limit]

    print(f"Preparing Stripe products for {len(ids)} artworks.")
    links_by_lookup_key = payment_links_by_lookup_key()
    artwork_links: dict[str, dict[str, str]] = {}

    for index, art_id in enumerate(ids, start=1):
        art = artwork_record(art_id)
        existing_prices = {
            variant: find_price_by_lookup_key(lookup_key(config, art_id))
            for variant, config in VARIANTS.items()
        }
        product_id = next((price["product"] for price in existing_prices.values() if price), "")

        if product_id:
            update_product_metadata(product_id, art)
        else:
            product = stripe_post("products", product_fields(art))
            product_id = product["id"]

        artwork_links[art_id] = {}

        for variant, config in VARIANTS.items():
            price_lookup_key = lookup_key(config, art_id)
            price = existing_prices[variant]

            if not price:
                price = stripe_post("prices", {
                    "currency": "usd",
                    "unit_amount": str(config["amount"]),
                    "product": product_id,
                    "nickname": config["nickname"],
                    "lookup_key": price_lookup_key,
                    **art_metadata(art, variant),
                    **metadata_fields("metadata", config["metadata"]),
                })

            link_lookup_key = payment_link_lookup_key(config, art_id)
            payment_link = links_by_lookup_key.get(link_lookup_key)
            payment_link_price = payment_link_price_id(payment_link["id"]) if payment_link else ""

            if payment_link and payment_link_price == price["id"]:
                update_payment_link_metadata(payment_link["id"], art, variant, config, link_lookup_key)
            else:
                fields = {
                    "line_items[0][price]": price["id"],
                    "line_items[0][quantity]": "1",
                    "shipping_address_collection[allowed_countries][0]": "US",
                    "billing_address_collection": "auto",
                    **payment_link_metadata_fields(art, variant, config, link_lookup_key),
                }

                if variant == "framed":
                    fields.update(frame_color_custom_field())

                payment_link = stripe_post("payment_links", fields)
                links_by_lookup_key[link_lookup_key] = payment_link

            artwork_links[art_id][variant] = payment_link["url"]

        print(f"[{index}/{len(ids)}] {art_id} -> {product_id}")

    update_payment_links_js(payment_links_payload(artwork_links, real_legacy_payment_links(env_payment_links)))
    print(f"\nUpdated {PAYMENT_LINKS_PATH} with {len(artwork_links)} artwork link sets.")


if __name__ == "__main__":
    main()
