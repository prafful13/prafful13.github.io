from __future__ import annotations

import sys
from pathlib import Path

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".avif"}
MAX_BYTES = 500 * 1024  # 500 KB

ROOT = Path(__file__).parent.parent


def find_oversized_images() -> list[tuple[Path, int]]:
    oversized: list[tuple[Path, int]] = []
    for path in ROOT.rglob("*"):
        if path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        if any(part.startswith(".") for part in path.parts):
            continue
        size = path.stat().st_size
        if size > MAX_BYTES:
            oversized.append((path, size))
    return oversized


def main() -> int:
    oversized = find_oversized_images()
    if not oversized:
        print("✓ All committed images are within the 500 KB limit.")
        return 0

    print("✗ The following committed images exceed 500 KB:")
    for path, size in oversized:
        rel = path.relative_to(ROOT)
        print(f"  {rel}  ({size / 1024:.1f} KB)")
    print(
        "\nResize or compress these images before committing. "
        "External URLs (CDN/GitHub raw) are not checked here."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
