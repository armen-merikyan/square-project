#!/usr/bin/env python3
"""Verify generated artworks completed the gallery and Stripe-link cycle."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ART_DIR = ROOT / "art"
ARTWORK_DIR = ROOT / "artwork"
STRIPE_PREVIEW_DIR = ROOT / "stripe-previews"
MANIFEST_PATH = ART_DIR / "manifest.json"
HOMEPAGE_IDS_PATH = ART_DIR / "homepage-artwork-ids.json"
PAYMENT_LINKS_PATH = ROOT / "payment-links.js"
SITEMAP_PATH = ROOT / "sitemap.xml"
PAYMENT_LINKS_JS_PREFIX = "window.SQUARE_PROJECT_PAYMENT_LINKS = "
ART_ID_PATTERN = re.compile(r"^[0-9a-f]{64}$")
FRAME_COLORS = ("black", "white", "natural", "brown", "gold")
MAX_EXAMPLES = 20


class CheckReport:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.details: list[str] = []

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warning(self, message: str) -> None:
        self.warnings.append(message)

    def detail(self, message: str) -> None:
        self.details.append(message)


def load_json(path: Path, report: CheckReport) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        report.error(f"Missing file: {path.relative_to(ROOT)}")
    except json.JSONDecodeError as error:
        report.error(f"Invalid JSON in {path.relative_to(ROOT)}: {error}")
    return None


def sample(values: set[str] | list[str], limit: int = MAX_EXAMPLES) -> str:
    ordered = sorted(values)
    shown = ordered[:limit]
    suffix = "" if len(ordered) <= limit else f" ... and {len(ordered) - limit} more"
    return ", ".join(shown) + suffix


def error_set(report: CheckReport, label: str, values: set[str]) -> None:
    if values:
        report.error(f"{label}: {len(values)} ({sample(values)})")


def hex_art_ids_from_files(extension: str) -> set[str]:
    return {
        path.stem
        for path in ART_DIR.glob(f"*.{extension}")
        if ART_ID_PATTERN.fullmatch(path.stem)
    }


def manifest_ids(report: CheckReport) -> list[str]:
    manifest = load_json(MANIFEST_PATH, report)
    if not isinstance(manifest, dict):
        return []

    ids = manifest.get("artworkIds")
    if not isinstance(ids, list):
        report.error("art/manifest.json does not contain an artworkIds list.")
        return []

    string_ids = [str(art_id) for art_id in ids]
    invalid = {art_id for art_id in string_ids if not ART_ID_PATTERN.fullmatch(art_id)}
    error_set(report, "Manifest ids that are not 64-char lowercase hex ids", invalid)

    duplicates = {art_id for art_id in string_ids if string_ids.count(art_id) > 1}
    error_set(report, "Duplicate ids in manifest", duplicates)

    manifest_count = manifest.get("count")
    if manifest_count != len(string_ids):
        report.error(f"Manifest count is {manifest_count}, but artworkIds has {len(string_ids)} ids.")

    report.detail(f"Manifest artworks: {len(string_ids)}")
    return string_ids


def check_art_files(report: CheckReport, ids: list[str]) -> None:
    manifest_set = set(ids)
    json_ids = hex_art_ids_from_files("json")
    svg_ids = hex_art_ids_from_files("svg")
    complete_file_ids = json_ids & svg_ids

    report.detail(f"Artwork JSON files: {len(json_ids)}")
    report.detail(f"Artwork SVG files: {len(svg_ids)}")

    error_set(report, "JSON art files missing matching SVG", json_ids - svg_ids)
    error_set(report, "SVG art files missing matching JSON", svg_ids - json_ids)
    error_set(report, "Manifest ids missing complete JSON/SVG art files", manifest_set - complete_file_ids)
    error_set(report, "Complete JSON/SVG art files missing from manifest", complete_file_ids - manifest_set)

    for art_id in sorted(manifest_set & complete_file_ids):
        record = load_json(ART_DIR / f"{art_id}.json", report)
        if not isinstance(record, dict):
            continue

        pixels = record.get("pixels")
        if not isinstance(pixels, list) or len(pixels) != 64:
            report.error(f"art/{art_id}.json has {0 if not isinstance(pixels, list) else len(pixels)} pixels, expected 64.")

        if record.get("id") and str(record.get("id")) != art_id:
            report.error(f"art/{art_id}.json has id={record.get('id')!r}, expected {art_id!r}.")


def ids_from_chunk_file(path: Path, report: CheckReport) -> list[str]:
    payload = load_json(path, report)
    if not isinstance(payload, dict):
        return []

    records = payload.get("records")
    if not isinstance(records, list):
        report.error(f"{path.relative_to(ROOT)} does not contain a records list.")
        return []

    ids = [str(record.get("id", "")) for record in records if isinstance(record, dict)]
    if len(ids) != len(records):
        report.error(f"{path.relative_to(ROOT)} contains non-object records.")
    return ids


def check_chunks(report: CheckReport, ids: list[str]) -> None:
    manifest = load_json(MANIFEST_PATH, report)
    if not isinstance(manifest, dict):
        return

    expected_ids = set(ids)
    chunk_ids: list[str] = []
    for chunk in manifest.get("chunks", []):
        if not isinstance(chunk, dict):
            report.error("Manifest chunks contains a non-object entry.")
            continue

        path = ROOT / str(chunk.get("path", ""))
        ids_in_file = ids_from_chunk_file(path, report)
        chunk_ids.extend(ids_in_file)

        if chunk.get("count") != len(ids_in_file):
            report.error(f"{path.relative_to(ROOT)} count is {chunk.get('count')}, file has {len(ids_in_file)} records.")

    category_ids: list[str] = []
    for category in manifest.get("categories", []):
        if not isinstance(category, dict):
            report.error("Manifest categories contains a non-object entry.")
            continue

        path = ROOT / str(category.get("path", ""))
        ids_in_file = ids_from_chunk_file(path, report)
        category_ids.extend(ids_in_file)

        listed_ids = [str(value) for value in category.get("ids", [])] if isinstance(category.get("ids"), list) else []
        if listed_ids != ids_in_file:
            report.error(f"{path.relative_to(ROOT)} ids do not match its manifest category ids.")

    chunk_set = set(chunk_ids)
    category_set = set(category_ids)
    error_set(report, "Manifest chunk ids missing from artworkIds", chunk_set - expected_ids)
    error_set(report, "Manifest artworkIds missing from chunks", expected_ids - chunk_set)
    error_set(report, "Category ids missing from artworkIds", category_set - expected_ids)
    error_set(report, "Manifest artworkIds missing from categories", expected_ids - category_set)

    duplicate_chunk_ids = {art_id for art_id in chunk_ids if chunk_ids.count(art_id) > 1}
    duplicate_category_ids = {art_id for art_id in category_ids if category_ids.count(art_id) > 1}
    error_set(report, "Duplicate ids across manifest chunks", duplicate_chunk_ids)
    error_set(report, "Duplicate ids across category chunks", duplicate_category_ids)


def check_homepage_ids(report: CheckReport, ids: list[str]) -> None:
    payload = load_json(HOMEPAGE_IDS_PATH, report)
    if not isinstance(payload, dict):
        return

    homepage_ids = [str(value) for value in payload.get("artworkIds", [])] if isinstance(payload.get("artworkIds"), list) else []
    if payload.get("count") != len(homepage_ids):
        report.error(f"Homepage artwork count is {payload.get('count')}, but artworkIds has {len(homepage_ids)} ids.")

    missing = set(homepage_ids) - set(ids)
    error_set(report, "Homepage ids missing from manifest", missing)
    report.detail(f"Homepage artwork ids: {len(homepage_ids)}")


def check_static_pages(report: CheckReport, ids: list[str]) -> None:
    id_set = set(ids)
    page_ids = {
        path.parent.name
        for path in ARTWORK_DIR.glob("*/index.html")
        if ART_ID_PATTERN.fullmatch(path.parent.name)
    }
    sitemap_text = SITEMAP_PATH.read_text(encoding="utf-8") if SITEMAP_PATH.is_file() else ""

    report.detail(f"Static artwork pages: {len(page_ids)}")
    error_set(report, "Manifest ids missing static artwork page", id_set - page_ids)
    error_set(report, "Static artwork pages missing from manifest", page_ids - id_set)

    missing_sitemap = {
        art_id
        for art_id in id_set
        if f"/artwork/{art_id}/" not in sitemap_text
    }
    error_set(report, "Manifest ids missing sitemap artwork URL", missing_sitemap)


def payment_links_payload(report: CheckReport) -> dict[str, Any]:
    if not PAYMENT_LINKS_PATH.is_file():
        report.error(f"Missing file: {PAYMENT_LINKS_PATH.relative_to(ROOT)}")
        return {}

    text = PAYMENT_LINKS_PATH.read_text(encoding="utf-8").strip()
    if not text.startswith(PAYMENT_LINKS_JS_PREFIX):
        report.error("payment-links.js does not start with the expected window.SQUARE_PROJECT_PAYMENT_LINKS assignment.")
        return {}

    payload_text = text[len(PAYMENT_LINKS_JS_PREFIX):].strip()
    if payload_text.endswith(";"):
        payload_text = payload_text[:-1].strip()

    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError as error:
        report.error(f"Invalid JSON payload in payment-links.js: {error}")
        return {}

    return payload if isinstance(payload, dict) else {}


def is_real_payment_link(url: Any) -> bool:
    text = str(url or "").strip()
    return text.startswith("https://buy.") and "/b/" in text and "your-" not in text


def check_payment_links(report: CheckReport, ids: list[str]) -> tuple[dict[str, str], set[str]]:
    payload = payment_links_payload(report)
    artworks = payload.get("artworks") if isinstance(payload.get("artworks"), dict) else {}
    id_set = set(ids)
    artwork_link_ids = {str(art_id) for art_id in artworks}

    report.detail(f"Artwork payment-link sets: {len(artwork_link_ids)}")
    error_set(report, "Manifest ids missing payment-link set", id_set - artwork_link_ids)
    error_set(report, "Payment-link sets missing from manifest", artwork_link_ids - id_set)

    expected_urls_by_lookup: dict[str, str] = {}
    expected_lookup_keys: set[str] = set()
    missing_links: set[str] = set()
    invalid_links: set[str] = set()

    for art_id in ids:
        print_lookup = f"square_project_art_{art_id}_print_payment_link"
        expected_lookup_keys.add(print_lookup)
        framed_lookup_keys = {
            frame_color: f"square_project_art_{art_id}_framed_{frame_color}_payment_link"
            for frame_color in FRAME_COLORS
        }
        expected_lookup_keys.update(framed_lookup_keys.values())

        links = artworks.get(art_id)
        if not isinstance(links, dict):
            continue

        print_url = links.get("print")
        if is_real_payment_link(print_url):
            expected_urls_by_lookup[print_lookup] = str(print_url).strip()
        else:
            (missing_links if not print_url else invalid_links).add(f"{art_id}:print")

        framed = links.get("framed")
        if not isinstance(framed, dict):
            missing_links.update(f"{art_id}:framed:{frame_color}" for frame_color in FRAME_COLORS)
            continue

        for frame_color in FRAME_COLORS:
            url = framed.get(frame_color)
            lookup = framed_lookup_keys[frame_color]
            if is_real_payment_link(url):
                expected_urls_by_lookup[lookup] = str(url).strip()
            else:
                (missing_links if not url else invalid_links).add(f"{art_id}:framed:{frame_color}")

    error_set(report, "Missing payment links", missing_links)
    error_set(report, "Invalid payment links", invalid_links)
    report.detail(f"Expected per-artwork payment links: {len(ids) * (1 + len(FRAME_COLORS))}")
    report.detail(f"Configured real per-artwork payment links: {len(expected_urls_by_lookup)}")
    return expected_urls_by_lookup, expected_lookup_keys


def check_stripe_previews(report: CheckReport, ids: list[str]) -> None:
    expected = {
        f"{art_id}_{frame_color}.svg"
        for art_id in ids
        for frame_color in FRAME_COLORS
    }
    existing = {
        path.name
        for path in STRIPE_PREVIEW_DIR.glob("*.svg")
        if re.fullmatch(r"[0-9a-f]{64}_(black|white|natural|brown|gold)\.svg", path.name)
    }

    report.detail(f"Expected Stripe preview SVGs: {len(expected)}")
    report.detail(f"Existing Stripe preview SVGs: {len(existing)}")
    error_set(report, "Missing Stripe preview SVGs", expected - existing)
    error_set(report, "Extra Stripe preview SVGs not in manifest", existing - expected)


def check_stripe_api(
    report: CheckReport,
    expected_urls_by_lookup: dict[str, str],
    expected_lookup_keys: set[str],
) -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    import setup_stripe_shop  # pylint: disable=import-error,import-outside-toplevel

    setup_stripe_shop.load_env()
    if not setup_stripe_shop.os.environ.get("STRIPE_SECRET_KEY", "").strip():
        report.warning("Skipped Stripe API verification because STRIPE_SECRET_KEY is not set.")
        return

    links_by_lookup = setup_stripe_shop.payment_links_by_lookup_key()
    active_lookup_keys = set(links_by_lookup)

    report.detail(f"Active Stripe payment links with lookup_key metadata: {len(active_lookup_keys)}")
    error_set(report, "Expected payment links missing from Stripe API", expected_lookup_keys - active_lookup_keys)

    url_mismatches: set[str] = set()
    inactive_or_wrong_kind: set[str] = set()
    for lookup_key, expected_url in expected_urls_by_lookup.items():
        payment_link = links_by_lookup.get(lookup_key)
        if not payment_link:
            continue

        if payment_link.get("url") != expected_url:
            url_mismatches.add(lookup_key)
        if payment_link.get("active") is False or payment_link.get("metadata", {}).get("kind") != "artwork_order":
            inactive_or_wrong_kind.add(lookup_key)

    error_set(report, "Stripe API payment-link URL mismatches", url_mismatches)
    error_set(report, "Stripe API payment links inactive or missing artwork_order metadata", inactive_or_wrong_kind)


def run_checks(stripe_api: bool) -> CheckReport:
    report = CheckReport()
    ids = manifest_ids(report)

    if ids:
        check_art_files(report, ids)
        check_chunks(report, ids)
        check_homepage_ids(report, ids)
        check_static_pages(report, ids)
        check_stripe_previews(report, ids)
        expected_urls_by_lookup, expected_lookup_keys = check_payment_links(report, ids)

        if stripe_api:
            check_stripe_api(report, expected_urls_by_lookup, expected_lookup_keys)

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stripe-api",
        action="store_true",
        help="Also verify active Stripe payment links by metadata lookup_key using STRIPE_SECRET_KEY.",
    )
    args = parser.parse_args()

    report = run_checks(args.stripe_api)

    for detail in report.details:
        print(f"ok: {detail}")
    for warning in report.warnings:
        print(f"warning: {warning}")
    for error in report.errors:
        print(f"error: {error}")

    if report.errors:
        print(f"\nFAILED: {len(report.errors)} issue groups found.")
        return 1

    print("\nPASS: all artwork cycle checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
