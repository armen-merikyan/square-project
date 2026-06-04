#!/usr/bin/env python3
"""Repair Stripe Product image URLs for existing Square Project listings.

This script is the single Stripe image repair path. It uses the listings in
payment-links.js, resolves each listing to its Stripe Price by lookup key,
generates framed preview SVGs when needed, and updates the related Product
images array to the expected artwork or framed preview URL.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

import setup_stripe_shop as shop


STATE_PATH = shop.ROOT / ".stripe-product-image-fix.json"
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
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Resolve listings and report image changes without updating Stripe.",
    )
    parser.add_argument(
        "--check-urls",
        action="store_true",
        help="Check each expected image URL is publicly reachable before updating Stripe.",
    )
    parser.add_argument(
        "--variant",
        choices=("all", "print", "framed"),
        default="all",
        help="Listing variant to repair. Defaults to all.",
    )
    parser.add_argument(
        "--art-id",
        action="append",
        default=[],
        help="Artwork ID to repair. Can be passed more than once. Defaults to all configured artwork.",
    )
    parser.add_argument(
        "--generate-previews-only",
        action="store_true",
        help="Only write local framed preview SVGs for matching framed listings; do not call Stripe.",
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


def iter_configured_listings(
    artwork_links: dict[str, dict],
    variant_filter: str = "all",
    art_ids: set[str] | None = None,
) -> list[dict[str, str]]:
    listings: list[dict[str, str]] = []

    for art_id in sorted(artwork_links):
        if art_ids and art_id not in art_ids:
            continue

        links = artwork_links[art_id]
        print_url = str(links.get("print") or "").strip()

        if variant_filter in {"all", "print"} and shop.is_real_payment_link(print_url):
            listings.append({
                "art_id": art_id,
                "variant": "print",
                "frame_color": "",
                "url": print_url,
                "key": listing_key(art_id, "print", None),
            })

        framed_links = links.get("framed")
        if variant_filter in {"all", "framed"} and isinstance(framed_links, dict):
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


def image_url_is_reachable(image_url: str) -> bool:
    request = urllib.request.Request(image_url, method="HEAD")

    try:
        with urllib.request.urlopen(request, timeout=10, context=shop.STRIPE_CONTEXT) as response:
            return 200 <= response.status < 400
    except urllib.error.HTTPError as error:
        if error.code not in {403, 405}:
            return False
    except urllib.error.URLError:
        return False

    request = urllib.request.Request(image_url, method="GET")

    try:
        with urllib.request.urlopen(request, timeout=10, context=shop.STRIPE_CONTEXT) as response:
            return 200 <= response.status < 400
    except urllib.error.URLError:
        return False


def generate_framed_preview(listing: dict[str, str]) -> tuple[str, str]:
    if listing["variant"] != "framed" or not listing["frame_color"]:
        return listing["key"], "skipped non-framed listing"

    art = shop.artwork_record(listing["art_id"])
    shop.write_framed_preview_svg(art, listing["frame_color"])
    return listing["key"], "wrote preview"


def update_product_image(
    listing: dict[str, str],
    dry_run: bool,
    check_urls: bool,
) -> tuple[str, str]:
    frame_color = listing["frame_color"] or None
    variant = listing["variant"]
    config = shop.VARIANTS[variant]
    price_lookup_key = shop.lookup_key(config, listing["art_id"], frame_color)
    price = shop.find_price_by_lookup_key(price_lookup_key)

    if not price:
        return listing["key"], f"missing active price for lookup key {price_lookup_key}"

    product_id = str(price.get("product") or "")

    if not product_id:
        return listing["key"], f"price {price.get('id') or price_lookup_key} has no product"

    art = shop.artwork_record(listing["art_id"])

    if frame_color:
        shop.write_framed_preview_svg(art, frame_color)

    expected_image_url = shop.image_url_for_variant(art, variant, frame_color)

    if check_urls and not image_url_is_reachable(expected_image_url):
        return listing["key"], f"image URL not reachable: {expected_image_url}"

    product = shop.stripe_get(f"products/{product_id}", {})
    current_images = product.get("images")
    current_first_image = current_images[0] if isinstance(current_images, list) and current_images else ""

    if current_first_image == expected_image_url:
        return listing["key"], "already correct"

    if dry_run:
        return listing["key"], f"would update {product_id}"

    fields = shop.product_fields(art, variant, frame_color, product_id)
    fields["images[0]"] = expected_image_url
    fields["metadata[art_image_url]"] = shop.stripe_metadata_value(expected_image_url)
    shop.stripe_post(f"products/{product_id}", fields)
    return listing["key"], f"updated {product_id}"


def main() -> None:
    shop.load_env()
    args = parse_args()

    artwork_links = configured_artwork_links()
    art_ids = {str(art_id).strip() for art_id in args.art_id if str(art_id).strip()}
    listings = iter_configured_listings(artwork_links, args.variant, art_ids)
    state = load_state(args.restart or args.dry_run)
    completed = state.setdefault("completed", {})

    if not args.generate_previews_only and not args.restart and not args.dry_run:
        listings = [
            listing
            for listing in listings
            if not completed_successfully(completed.get(listing["key"]))
        ]

    if args.limit > 0:
        listings = listings[:args.limit]

    if not listings:
        action = "previews to generate" if args.generate_previews_only else "Stripe product images need repair"
        print(f"No existing {action}.")
        if not args.dry_run:
            save_state(state)
        return

    if args.generate_previews_only:
        listings = [listing for listing in listings if listing["variant"] == "framed" and listing["frame_color"]]
        print(f"Generating framed preview SVGs for {len(listings)} configured framed listings...", flush=True)
        started_at = time.time()
        written = 0

        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
            futures = {executor.submit(generate_framed_preview, listing): listing for listing in listings}

            for index, future in enumerate(as_completed(futures), start=1):
                listing = futures[future]

                try:
                    _, result = future.result()
                except Exception as error:  # noqa: BLE001 - keep a long generation run resumable.
                    print(f"[{index}/{len(listings)}] {listing['key']} -> failed: {error}", flush=True)
                    continue

                if result == "wrote preview":
                    written += 1

                if index % 500 == 0 or index == len(listings):
                    print(f"[{index}/{len(listings)}] wrote {written} previews", flush=True)

        elapsed = time.time() - started_at
        print(f"Generated {written} framed preview SVGs in {elapsed:.1f}s.")
        return

    if not shop.os.environ.get("STRIPE_SECRET_KEY", "").strip():
        raise SystemExit("Set STRIPE_SECRET_KEY in .env before running this script.")

    lock = Lock()
    started_at = time.time()
    action = "Checking" if args.dry_run else "Repairing"
    print(f"{action} product images on {len(listings)} existing Stripe listings...", flush=True)

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = {
            executor.submit(
                update_product_image,
                listing,
                args.dry_run,
                args.check_urls,
            ): listing
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
    mode = "check" if args.dry_run else "repair"
    print(f"Product image {mode} complete for {len(listings)} listings in {elapsed:.1f}s.")


if __name__ == "__main__":
    main()
