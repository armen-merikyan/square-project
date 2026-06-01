#!/usr/bin/env python3

from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ART_DIR = PROJECT_ROOT / "art"
MANIFEST_PATH = ART_DIR / "manifest.json"


def main() -> int:
    ART_DIR.mkdir(parents=True, exist_ok=True)

    json_ids = {path.stem for path in ART_DIR.glob("*.json") if path.name != MANIFEST_PATH.name}
    svg_ids = {path.stem for path in ART_DIR.glob("*.svg")}
    artwork_ids = sorted(json_ids & svg_ids)

    manifest = {
        "artworkIds": artwork_ids,
        "count": len(artwork_ids),
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {MANIFEST_PATH.relative_to(PROJECT_ROOT)} with {len(artwork_ids)} artworks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
