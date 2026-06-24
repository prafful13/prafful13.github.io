from __future__ import annotations

import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).parent.parent


class _MediaValidator(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.issues: list[str] = []
        self.images: list[dict] = []
        self.videos: list[dict] = []
        self.in_style = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "style":
            self.in_style = True
            return

        if tag == "img":
            attr_dict = dict(attrs)
            img_info = {
                "src": attr_dict.get("src", ""),
                "alt": attr_dict.get("alt", ""),
                "width": attr_dict.get("width"),
                "height": attr_dict.get("height"),
                "loading": attr_dict.get("loading", ""),
            }
            self.images.append(img_info)

            src = img_info["src"]
            if not src:
                self.issues.append("Found <img> with empty src")
            if not img_info["alt"]:
                self.issues.append(f"Image {src} missing alt text")
            if not img_info["width"]:
                self.issues.append(f"Image {src} missing width attribute")
            if not img_info["height"]:
                self.issues.append(f"Image {src} missing height attribute")
            if img_info["loading"] != "lazy":
                self.issues.append(f"Image {src} missing loading='lazy'")

        elif tag == "video":
            attr_dict = dict(attrs)
            video_info = {
                "width": attr_dict.get("width"),
                "height": attr_dict.get("height"),
                "autoplay": "autoplay" in attr_dict,
                "muted": "muted" in attr_dict,
                "loop": "loop" in attr_dict,
                "playsinline": "playsinline" in attr_dict,
            }
            self.videos.append(video_info)

            if not video_info["width"]:
                self.issues.append("Found <video> without explicit width")
            if not video_info["height"]:
                self.issues.append("Found <video> without explicit height")
            if not video_info["autoplay"]:
                self.issues.append("Found <video> without autoplay")
            if not video_info["muted"]:
                self.issues.append("Found <video> without muted")
            if not video_info["loop"]:
                self.issues.append("Found <video> without loop")
            if not video_info["playsinline"]:
                self.issues.append("Found <video> without playsinline")

    def handle_endtag(self, tag: str) -> None:
        if tag == "style":
            self.in_style = False


def validate_media(html_path: Path) -> tuple[list[str], _MediaValidator]:
    content = html_path.read_text(encoding="utf-8")
    validator = _MediaValidator()
    validator.feed(content)
    return validator.issues, validator


def main() -> int:
    index = ROOT / "index.html"
    issues, validator = validate_media(index)

    if not issues:
        print("✓ All media elements are properly optimized:")
        print(f"  - {len(validator.images)} images with explicit dimensions and lazy loading")
        print(f"  - {len(validator.videos)} video elements with autoplay, muted, loop, playsinline")
        return 0

    print("✗ Media optimization issues found:")
    for issue in issues:
        print(f"  - {issue}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
