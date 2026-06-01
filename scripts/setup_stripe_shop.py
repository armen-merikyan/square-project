#!/usr/bin/env python3
"""Publish or create the Stripe payment links for Square Project."""

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
STRIPE_CONTEXT = ssl.create_default_context(cafile=certifi.where()) if certifi else None
VARIANTS = {
    "print": {
        "nickname": "Square Project 8x8 Art Print",
        "amount": 2400,
        "lookup_key": "square_project_8x8_print",
        "env_key": "STRIPE_PRINT_PRICE_ID",
        "payment_link_env_key": "STRIPE_PRINT_PAYMENT_LINK",
        "payment_link_lookup_key": "square_project_8x8_print_payment_link",
        "metadata": {
            "variant": "print",
            "image_area": "8x8",
            "frame_size": "none",
        },
    },
    "framed": {
        "nickname": "Square Project 12x12 Framed Print",
        "amount": 3900,
        "lookup_key": "square_project_12x12_framed",
        "env_key": "STRIPE_FRAMED_PRICE_ID",
        "payment_link_env_key": "STRIPE_FRAMED_PAYMENT_LINK",
        "payment_link_lookup_key": "square_project_12x12_framed_payment_link",
        "metadata": {
            "variant": "framed",
            "image_area": "8x8",
            "frame_size": "12x12",
            "frame_colors": "black,white,natural,brown,gold",
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


def update_payment_links_js(payment_links: dict[str, str]) -> None:
    payload = json.dumps(payment_links, indent=2, sort_keys=True)
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


def find_payment_link_by_lookup_key(lookup_key: str) -> dict | None:
    for payment_link in iter_payment_links():
        if payment_link.get("metadata", {}).get("lookup_key") == lookup_key:
            return payment_link

    return None


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


def update_product_metadata(product_id: str) -> None:
    stripe_post(f"products/{product_id}", {
        "name": "Square Project 8x8 Art Order",
        "description": (
            "Square Project reusable catalog product for static-site orders. "
            "Order identity is passed through Payment Link client_reference_id as "
            "art_<art_id>_variant_<print|framed>_frame_<color|none>."
        ),
        "metadata[app]": "square_project",
        "metadata[kind]": "art_order",
        "metadata[site]": "mysquareart.com",
        "metadata[order_reference_format]": "art_<art_id>_variant_<variant>_frame_<frame_color>",
    })


def update_payment_link_metadata(payment_link_id: str, variant: str, config: dict) -> None:
    fields = {
        "metadata[app]": "square_project",
        "metadata[variant]": variant,
        "metadata[lookup_key]": config["payment_link_lookup_key"],
        "metadata[order_reference_format]": "art_<art_id>_variant_<variant>_frame_<frame_color>",
    }

    for key, value in config["metadata"].items():
        fields[f"metadata[{key}]"] = value

    stripe_post(f"payment_links/{payment_link_id}", fields)


def main() -> None:
    load_env()
    env_payment_links = {
        variant: os.environ.get(config["payment_link_env_key"], "").strip()
        for variant, config in VARIANTS.items()
    }

    secret_key = os.environ.get("STRIPE_SECRET_KEY", "").strip()

    if all(is_real_payment_link(url) for url in env_payment_links.values()) and not secret_key:
        update_payment_links_js(env_payment_links)
        print(f"Updated {PAYMENT_LINKS_PATH} from existing Stripe Payment Links in {ENV_PATH}.")
        return

    if any(env_payment_links.values()) and not all(
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
            "For this static site, add STRIPE_PRINT_PAYMENT_LINK and "
            "STRIPE_FRAMED_PAYMENT_LINK Stripe Payment Link URLs to .env, then rerun this script. "
            "STRIPE_SECRET_KEY is only needed if you want this script to create Stripe links."
        )

    product_id = os.environ.get("STRIPE_ART_PRODUCT_ID", "").strip()

    if not is_real_stripe_id(product_id, "prod_"):
        product_id = ""

    existing_prices = {
        variant: find_price_by_lookup_key(config["lookup_key"])
        for variant, config in VARIANTS.items()
    }

    if not product_id:
        product_id = next(
            (price["product"] for price in existing_prices.values() if price),
            "",
        )

    if product_id:
        print(f"Using existing product: {product_id}")
    else:
        product = stripe_post("products", {
            "name": "Square Project 8x8 Art Order",
            "description": (
                "Square Project reusable catalog product for static-site orders. "
                "Order identity is passed through Payment Link client_reference_id as "
                "art_<art_id>_variant_<print|framed>_frame_<color|none>."
            ),
            "metadata[app]": "square_project",
            "metadata[kind]": "art_order",
            "metadata[site]": "mysquareart.com",
            "metadata[order_reference_format]": "art_<art_id>_variant_<variant>_frame_<frame_color>",
        })
        product_id = product["id"]
        print(f"Created product: {product_id}")

    update_product_metadata(product_id)

    created_prices = {}
    created_payment_links = {}

    for variant, config in VARIANTS.items():
        existing_price = os.environ.get(config["env_key"], "").strip()

        if is_real_stripe_id(existing_price, "price_"):
            created_prices[config["env_key"]] = existing_price
            print(f"Using existing {variant} price: {existing_price}")
            continue

        lookup_price = existing_prices[variant]

        if lookup_price:
            created_prices[config["env_key"]] = lookup_price["id"]
            print(f"Using existing {variant} price: {lookup_price['id']}")
            continue

        price = stripe_post("prices", {
            "currency": "usd",
            "unit_amount": str(config["amount"]),
            "product": product_id,
            "nickname": config["nickname"],
            "lookup_key": config["lookup_key"],
            **{
                f"metadata[{key}]": value
                for key, value in config["metadata"].items()
            },
        })
        created_prices[config["env_key"]] = price["id"]
        print(f"Created {variant} price: {price['id']}")

    for variant, config in VARIANTS.items():
        existing_payment_link = os.environ.get(config["payment_link_env_key"], "").strip()

        env_payment_link = find_payment_link_by_url(existing_payment_link)
        env_price_id = payment_link_price_id(env_payment_link["id"]) if env_payment_link else ""
        if env_payment_link and env_price_id == created_prices[config["env_key"]]:
            update_payment_link_metadata(env_payment_link["id"], variant, config)
            created_payment_links[variant] = env_payment_link["url"]
            print(f"Using existing {variant} payment link: {env_payment_link['url']}")
            continue

        lookup_payment_link = find_payment_link_by_lookup_key(config["payment_link_lookup_key"])
        lookup_price_id = (
            payment_link_price_id(lookup_payment_link["id"]) if lookup_payment_link else ""
        )

        if lookup_payment_link and lookup_price_id == created_prices[config["env_key"]]:
            update_payment_link_metadata(lookup_payment_link["id"], variant, config)
            created_payment_links[variant] = lookup_payment_link["url"]
            print(f"Using existing {variant} payment link: {lookup_payment_link['url']}")
            continue

        fields = {
            "line_items[0][price]": created_prices[config["env_key"]],
            "line_items[0][quantity]": "1",
            "metadata[app]": "square_project",
            "metadata[variant]": variant,
            "metadata[lookup_key]": config["payment_link_lookup_key"],
            "metadata[order_reference_format]": "art_<art_id>_variant_<variant>_frame_<frame_color>",
            "shipping_address_collection[allowed_countries][0]": "US",
            "billing_address_collection": "auto",
        }

        for key, value in config["metadata"].items():
            fields[f"metadata[{key}]"] = value

        payment_link = stripe_post("payment_links", fields)
        created_payment_links[variant] = payment_link["url"]
        print(f"Created {variant} payment link: {payment_link['url']}")

    payment_link_env_updates = {
        VARIANTS[variant]["payment_link_env_key"]: url
        for variant, url in created_payment_links.items()
    }
    updates = {"STRIPE_ART_PRODUCT_ID": product_id, **created_prices, **payment_link_env_updates}
    update_env(updates)
    update_payment_links_js(created_payment_links)

    print(f"\nUpdated {ENV_PATH}:")
    for key, value in updates.items():
        print(f"{key}={value}")
    print(f"\nUpdated {PAYMENT_LINKS_PATH}")


if __name__ == "__main__":
    main()
