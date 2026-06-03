#!/usr/bin/env python3
"""Repair fulfillment metadata on existing Stripe listings.

This script does not create Stripe products, prices, or payment links. It uses
the existing per-artwork URLs in payment-links.js, resolves each Stripe Payment
Link, and updates the related Product, Price, Payment Link, and future
PaymentIntent metadata so fulfillment fields are visible in Stripe.
"""

from __future__ import annotations

import argparse
import urllib.parse
import urllib.request
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

import setup_stripe_shop as shop


STATE_PATH = shop.ROOT / ".stripe-listing-metadata-fix.json"
STATE_VERSION = 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Maximum number of listing variants to process. Defaults to all existing links.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=int(shop.os.environ.get("STRIPE_FIX_WORKERS", "4") or "4"),
        help="Concurrent repair workers. Defaults to STRIPE_FIX_WORKERS or 4.",
    )
    parser.add_argument(
        "--restart",
        action="store_true",
        help="Ignore prior repair state and process matching listings again.",
    )
    return parser.parse_args()


def load_state(restart: bool) -> dict:
    if restart or not STATE_PATH.is_file():
        return {"version": STATE_VERSION, "completed": {}}

    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"version": STATE_VERSION, "completed": {}}

    if not isinstance(state, dict) or state.get("version") != STATE_VERSION:
        return {"version": STATE_VERSION, "completed": {}}

    completed = state.get("completed")
    if not isinstance(completed, dict):
        state["completed"] = {}

    return state


def save_state(state: dict) -> None:
    state["version"] = STATE_VERSION
    state.setdefault("completed", {})
    STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def configured_artwork_links() -> dict[str, dict]:
    payload = shop.existing_payment_links_payload()
    artworks = payload.get("artworks")

    if not isinstance(artworks, dict):
        raise SystemExit(f"{shop.PAYMENT_LINKS_PATH} does not contain an artworks payment-link map.")

    return {
        str(art_id): links
        for art_id, links in artworks.items()
        if isinstance(links, dict)
    }


def listing_key(art_id: str, variant: str, frame_color: str | None) -> str:
    return shop.fulfillment_id({"id": art_id}, variant, frame_color)


def iter_configured_listings(artwork_links: dict[str, dict]) -> list[dict[str, str]]:
    listings: list[dict[str, str]] = []

    for art_id in sorted(artwork_links):
        links = artwork_links[art_id]
        print_url = str(links.get("print") or "").strip()

        if shop.is_real_payment_link(print_url):
            listings.append({
                "art_id": art_id,
                "variant": "print",
                "frame_color": "",
                "url": print_url,
                "key": listing_key(art_id, "print", None),
            })

        framed_links = links.get("framed")
        if isinstance(framed_links, dict):
            for frame_color in shop.FRAME_COLORS:
                framed_url = str(framed_links.get(frame_color) or "").strip()

                if shop.is_real_payment_link(framed_url):
                    listings.append({
                        "art_id": art_id,
                        "variant": "framed",
                        "frame_color": frame_color,
                        "url": framed_url,
                        "key": listing_key(art_id, "framed", frame_color),
                    })

    return listings


def payment_links_by_url() -> dict[str, dict]:
    links: dict[str, dict] = {}
    starting_after = ""
    page = 0

    while True:
        page += 1
        fields = {
            "active": "true",
            "limit": "100",
        }

        if starting_after:
            fields["starting_after"] = starting_after

        print(f"Loading Stripe Payment Link page {page}...", flush=True)
        payment_links = stripe_get_with_timeout("payment_links", fields, timeout=10)
        data = payment_links.get("data", [])

        for payment_link in data:
            url = payment_link.get("url")

            if url:
                links[str(url)] = payment_link

        print(f"Loaded page {page}: {len(data)} links ({len(links)} total).", flush=True)

        if not payment_links.get("has_more") or not data:
            break

        starting_after = data[-1]["id"]

    return links


def stripe_get_with_timeout(path: str, fields: dict[str, str], timeout: int = 10) -> dict:
    secret_key = shop.os.environ.get("STRIPE_SECRET_KEY", "").strip()
    url = f"https://api.stripe.com/v1/{path.lstrip('/')}?{urllib.parse.urlencode(fields)}"
    request = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {secret_key}"},
        method="GET",
    )

    with urllib.request.urlopen(request, timeout=timeout, context=shop.STRIPE_CONTEXT) as response:
        return json.loads(response.read().decode("utf-8"))


def payment_link_line_item_refs(payment_link_id: str) -> tuple[str, str]:
    line_items = shop.stripe_get(f"payment_links/{payment_link_id}/line_items", {"limit": "1"})
    data = line_items.get("data", [])

    if not data:
        return "", ""

    price = data[0].get("price")
    if not isinstance(price, dict):
        return "", ""

    product = price.get("product")
    return str(price.get("id") or ""), str(product or "")


def repair_listing(listing: dict[str, str], payment_link: dict) -> tuple[str, str]:
    frame_color = listing["frame_color"] or None
    variant = listing["variant"]
    config = shop.VARIANTS[variant]
    payment_link_id = str(payment_link["id"])
    price_id, product_id = payment_link_line_item_refs(payment_link_id)

    if not price_id or not product_id:
        return listing["key"], "missing line item"

    art = shop.artwork_record(listing["art_id"])
    lookup_key = shop.payment_link_lookup_key(config, listing["art_id"], frame_color)

    shop.update_product_metadata(product_id, art, variant, frame_color)
    shop.update_price_metadata(price_id, art, variant, config, product_id, frame_color)
    shop.update_payment_link_metadata(
        payment_link_id,
        art,
        variant,
        config,
        lookup_key,
        product_id,
        price_id,
        frame_color,
    )

    return listing["key"], "updated"


def main() -> None:
    shop.load_env()
    args = parse_args()

    if not shop.os.environ.get("STRIPE_SECRET_KEY", "").strip():
        raise SystemExit("Set STRIPE_SECRET_KEY in .env before running this script.")

    artwork_links = configured_artwork_links()
    listings = iter_configured_listings(artwork_links)
    state = load_state(args.restart)
    completed = state.setdefault("completed", {})

    if not args.restart:
        listings = [listing for listing in listings if listing["key"] not in completed]

    if args.limit > 0:
        listings = listings[:args.limit]

    print(f"Loading active Stripe Payment Links for {len(listings)} listings...", flush=True)
    links_by_url = payment_links_by_url()
    print(f"Loaded {len(links_by_url)} active Stripe Payment Links.", flush=True)

    repairable = [listing for listing in listings if listing["url"] in links_by_url]
    missing = len(listings) - len(repairable)

    if missing:
        print(f"Skipping {missing} configured links that are not active in Stripe.", flush=True)

    if not repairable:
        print("No existing Stripe listings need metadata repair.")
        save_state(state)
        return

    lock = Lock()
    started_at = time.time()
    print(f"Repairing metadata on {len(repairable)} existing Stripe listings...", flush=True)

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = {
            executor.submit(repair_listing, listing, links_by_url[listing["url"]]): listing
            for listing in repairable
        }

        for index, future in enumerate(as_completed(futures), start=1):
            listing = futures[future]

            try:
                key, result = future.result()
            except Exception as error:  # noqa: BLE001 - keep a long repair run resumable.
                print(f"[{index}/{len(repairable)}] {listing['key']} -> failed: {error}", flush=True)
                continue

            with lock:
                completed[key] = {
                    "result": result,
                    "repaired_at": int(time.time()),
                }

                if index % 25 == 0 or index == len(repairable):
                    save_state(state)

            print(f"[{index}/{len(repairable)}] {key} -> {result}", flush=True)

    save_state(state)
    elapsed = time.time() - started_at
    print(f"Metadata repair complete for {len(repairable)} listings in {elapsed:.1f}s.")


if __name__ == "__main__":
    main()
