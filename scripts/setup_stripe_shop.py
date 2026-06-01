#!/usr/bin/env python3
"""Create the reusable Stripe product and prices for Square Project checkout."""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from pathlib import Path
from urllib.error import HTTPError


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
VARIANTS = {
    "print": {
        "nickname": "Square Project 8x8 Art Print",
        "amount": 2400,
        "lookup_key": "square_project_8x8_print",
        "env_key": "STRIPE_PRINT_PRICE_ID",
    },
    "framed": {
        "nickname": "Square Project 8x8 Framed Print",
        "amount": 3900,
        "lookup_key": "square_project_8x8_framed",
        "env_key": "STRIPE_FRAMED_PRICE_ID",
    },
}


def clean_env_value(value: str) -> str:
    return value.strip().strip("\"'")


def is_real_stripe_id(value: str, prefix: str) -> bool:
    return value.startswith(prefix) and "_your" not in value and "your-" not in value


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
        with urllib.request.urlopen(request, timeout=20) as response:
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
        with urllib.request.urlopen(request, timeout=20) as response:
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


def main() -> None:
    load_env()
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
            "description": "Reusable product for Square Project 8x8 print orders.",
            "metadata[app]": "square_project",
            "metadata[kind]": "art_order",
        })
        product_id = product["id"]
        print(f"Created product: {product_id}")

    created_prices = {}

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
            "metadata[variant]": variant,
        })
        created_prices[config["env_key"]] = price["id"]
        print(f"Created {variant} price: {price['id']}")

    updates = {"STRIPE_ART_PRODUCT_ID": product_id, **created_prices}
    update_env(updates)

    print(f"\nUpdated {ENV_PATH}:")
    for key, value in updates.items():
        print(f"{key}={value}")


if __name__ == "__main__":
    main()
