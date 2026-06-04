#!/usr/bin/env python3
"""Update framed Stripe Products to use frame-specific preview images."""

from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

import setup_stripe_shop as shop
from fix_stripe_product_images import image_url_is_reachable


STATE_PATH = shop.ROOT / ".stripe-framed-product-image-fix.json"
STATE_VERSION = 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Maximum number of framed listing variants to process. Defaults to all framed links.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=int(shop.os.environ.get("STRIPE_FIX_WORKERS", "8") or "8"),
        help="Concurrent repair workers. Defaults to STRIPE_FIX_WORKERS or 8.",
    )
    parser.add_argument(
        "--restart",
        action="store_true",
        help="Ignore prior framed-image repair state and process matching listings again.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Resolve listings and report image changes without updating Stripe.",
    )
    parser.add_argument(
        "--allow-unreachable",
        action="store_true",
        help="Update Stripe even if the framed preview URL does not return 200 yet.",
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


def completed_successfully(entry: object) -> bool:
    if not isinstance(entry, dict):
        return False

    result = str(entry.get("result") or "")
    return result == "already correct" or result.startswith("updated ")


def framed_listings() -> list[dict[str, str]]:
    payload = shop.existing_payment_links_payload()
    artworks = payload.get("artworks")

    if not isinstance(artworks, dict):
        raise SystemExit(f"{shop.PAYMENT_LINKS_PATH} does not contain an artworks payment-link map.")

    listings: list[dict[str, str]] = []

    for art_id in sorted(artworks):
        links = artworks[art_id]
        if not isinstance(links, dict):
            continue

        framed = links.get("framed")
        if not isinstance(framed, dict):
            continue

        for frame_color in shop.FRAME_COLORS:
            framed_url = str(framed.get(frame_color) or "").strip()

            if not shop.is_real_payment_link(framed_url):
                continue

            listings.append({
                "art_id": str(art_id),
                "frame_color": frame_color,
                "key": shop.fulfillment_id({"id": str(art_id)}, "framed", frame_color),
            })

    return listings


def update_listing(listing: dict[str, str], dry_run: bool, allow_unreachable: bool) -> tuple[str, str]:
    art_id = listing["art_id"]
    frame_color = listing["frame_color"]
    config = shop.VARIANTS["framed"]
    price_lookup_key = shop.lookup_key(config, art_id, frame_color)
    price = shop.find_price_by_lookup_key(price_lookup_key)

    if not price:
        return listing["key"], f"missing active price for lookup key {price_lookup_key}"

    product_id = str(price.get("product") or "")

    if not product_id:
        return listing["key"], f"price {price.get('id') or price_lookup_key} has no product"

    art = shop.artwork_record(art_id)
    shop.write_framed_preview_svg(art, frame_color)
    image_url = shop.image_url_for_variant(art, "framed", frame_color)

    if not allow_unreachable and not image_url_is_reachable(image_url):
        return listing["key"], f"image URL not reachable: {image_url}"

    product = shop.stripe_get(f"products/{product_id}", {})
    current_images = product.get("images")
    current_first_image = current_images[0] if isinstance(current_images, list) and current_images else ""

    if current_first_image == image_url:
        return listing["key"], "already correct"

    if dry_run:
        return listing["key"], f"would update {product_id}"

    fields = shop.product_fields(art, "framed", frame_color, product_id)
    fields["images[0]"] = image_url
    fields["metadata[art_image_url]"] = shop.stripe_metadata_value(image_url)
    shop.stripe_post(f"products/{product_id}", fields)
    return listing["key"], f"updated {product_id}"


def main() -> None:
    shop.load_env()
    args = parse_args()

    if not shop.os.environ.get("STRIPE_SECRET_KEY", "").strip():
        raise SystemExit("Set STRIPE_SECRET_KEY in .env before running this script.")

    listings = framed_listings()
    state = load_state(args.restart or args.dry_run)
    completed = state.setdefault("completed", {})

    if not args.restart and not args.dry_run:
        listings = [
            listing
            for listing in listings
            if not completed_successfully(completed.get(listing["key"]))
        ]

    if args.limit > 0:
        listings = listings[:args.limit]

    if not listings:
        print("No framed Stripe product images need repair.")
        if not args.dry_run:
            save_state(state)
        return

    lock = Lock()
    started_at = time.time()
    action = "Checking" if args.dry_run else "Updating"
    print(f"{action} framed product images on {len(listings)} Stripe listings...", flush=True)

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = {
            executor.submit(update_listing, listing, args.dry_run, args.allow_unreachable): listing
            for listing in listings
        }

        for index, future in enumerate(as_completed(futures), start=1):
            listing = futures[future]

            try:
                key, result = future.result()
            except Exception as error:  # noqa: BLE001 - keep a long repair run resumable.
                print(f"[{index}/{len(listings)}] {listing['key']} -> failed: {error}", flush=True)
                continue

            if not args.dry_run:
                with lock:
                    completed[key] = {
                        "result": result,
                        "repaired_at": int(time.time()),
                    }

                    if index % 25 == 0 or index == len(listings):
                        save_state(state)

            print(f"[{index}/{len(listings)}] {key} -> {result}", flush=True)

    if not args.dry_run:
        save_state(state)

    elapsed = time.time() - started_at
    mode = "check" if args.dry_run else "update"
    print(f"Framed product image {mode} complete for {len(listings)} listings in {elapsed:.1f}s.")


if __name__ == "__main__":
    main()
