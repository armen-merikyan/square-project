#!/usr/bin/env python3
"""Generate framed Stripe preview SVGs for configured Payment Link listings."""

from __future__ import annotations

import argparse
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import setup_stripe_shop as shop


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Maximum number of artwork records to process. Defaults to all configured artwork.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=int(shop.os.environ.get("STRIPE_PREVIEW_WORKERS", "8") or "8"),
        help="Concurrent preview workers. Defaults to STRIPE_PREVIEW_WORKERS or 8.",
    )
    return parser.parse_args()


def configured_framed_artworks() -> dict[str, list[str]]:
    payload = shop.existing_payment_links_payload()
    artworks = payload.get("artworks")

    if not isinstance(artworks, dict):
        raise SystemExit(f"{shop.PAYMENT_LINKS_PATH} does not contain an artworks payment-link map.")

    configured: dict[str, list[str]] = {}

    for art_id, links in artworks.items():
        if not isinstance(links, dict):
            continue

        framed = links.get("framed")
        if not isinstance(framed, dict):
            continue

        frame_colors = [
            frame_color
            for frame_color in shop.FRAME_COLORS
            if shop.is_real_payment_link(str(framed.get(frame_color) or ""))
        ]

        if frame_colors:
            configured[str(art_id)] = frame_colors

    return configured


def generate_artwork_previews(art_id: str, frame_colors: list[str]) -> tuple[str, int]:
    art = shop.artwork_record(art_id)

    for frame_color in frame_colors:
        shop.write_framed_preview_svg(art, frame_color)

    return art_id, len(frame_colors)


def main() -> None:
    shop.load_env()
    args = parse_args()
    configured = configured_framed_artworks()
    items = sorted(configured.items())

    if not items:
        print("No configured framed Stripe previews need generation.")
        return

    if args_limit := args.limit:
        items = items[:args_limit]

    started_at = time.time()
    total_previews = sum(len(frame_colors) for _, frame_colors in items)
    print(
        f"Generating {total_previews} framed previews for {len(items)} artworks in {shop.STRIPE_PREVIEW_DIR}...",
        flush=True,
    )

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = {
            executor.submit(generate_artwork_previews, art_id, frame_colors): art_id
            for art_id, frame_colors in items
        }

        written = 0
        for index, future in enumerate(as_completed(futures), start=1):
            art_id, count = future.result()
            written += count

            if index % 100 == 0 or index == len(items):
                print(f"[{index}/{len(items)}] wrote {written}/{total_previews} previews; latest {art_id}", flush=True)

    elapsed = time.time() - started_at
    print(f"Generated {written} framed Stripe previews in {elapsed:.1f}s.")


if __name__ == "__main__":
    main()
