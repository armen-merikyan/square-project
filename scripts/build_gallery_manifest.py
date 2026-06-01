#!/usr/bin/env python3

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ART_DIR = PROJECT_ROOT / "art"
MANIFEST_PATH = ART_DIR / "manifest.json"


def build_gallery_manifest(art_dir: Path = ART_DIR, manifest_path: Path = MANIFEST_PATH) -> dict[str, Any]:
    art_dir.mkdir(parents=True, exist_ok=True)

    json_ids = {path.stem for path in art_dir.glob("*.json") if path.name != manifest_path.name}
    svg_ids = {path.stem for path in art_dir.glob("*.svg")}
    artwork_ids = sorted(
        json_ids & svg_ids,
        key=lambda artwork_id: (
            max((art_dir / f"{artwork_id}.json").stat().st_mtime, (art_dir / f"{artwork_id}.svg").stat().st_mtime),
            artwork_id,
        ),
        reverse=True,
    )

    manifest = {
        "artworkIds": artwork_ids,
        "count": len(artwork_ids),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    manifest = build_gallery_manifest()
    print(f"Wrote {MANIFEST_PATH.relative_to(PROJECT_ROOT)} with {manifest['count']} artworks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
