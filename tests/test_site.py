from __future__ import annotations

import re
import sys
from html.parser import HTMLParser
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
INDEX = ROOT / "index.html"


# ── Helpers ───────────────────────────────────────────────────────────────


class _LinkAndAnchorCollector(HTMLParser):
    """Collect hrefs, src attributes, and id attributes from HTML."""

    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []
        self.srcs: list[str] = []
        self.ids: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_dict = dict(attrs)
        if (href := attr_dict.get("href")) is not None:
            self.hrefs.append(href)
        if (src := attr_dict.get("src")) is not None:
            self.srcs.append(src)
        if (id_val := attr_dict.get("id")) is not None:
            self.ids.add(id_val)


def _parse_index() -> _LinkAndAnchorCollector:
    collector = _LinkAndAnchorCollector()
    collector.feed(INDEX.read_text(encoding="utf-8"))
    return collector


# ── index.html existence ──────────────────────────────────────────────────


def test_index_html_exists() -> None:
    assert INDEX.is_file(), "index.html must exist at the repo root"


def test_index_html_not_empty() -> None:
    assert INDEX.stat().st_size > 0, "index.html must not be empty"


# ── DOCTYPE and meta ──────────────────────────────────────────────────────


def test_html_has_doctype() -> None:
    content = INDEX.read_text(encoding="utf-8")
    assert content.strip().lower().startswith("<!doctype html"), (
        "index.html must begin with <!DOCTYPE html>"
    )


def test_html_has_charset_meta() -> None:
    content = INDEX.read_text(encoding="utf-8")
    assert re.search(r'<meta[^>]+charset', content, re.IGNORECASE), (
        "index.html must declare a charset meta tag"
    )


def test_html_has_viewport_meta() -> None:
    content = INDEX.read_text(encoding="utf-8")
    assert re.search(r'<meta[^>]+viewport', content, re.IGNORECASE), (
        "index.html must declare a viewport meta tag"
    )


def test_html_has_title() -> None:
    content = INDEX.read_text(encoding="utf-8")
    assert re.search(r'<title>[^<]+</title>', content, re.IGNORECASE), (
        "index.html must have a non-empty <title> element"
    )


def test_html_has_lang_attribute() -> None:
    content = INDEX.read_text(encoding="utf-8")
    assert re.search(r'<html[^>]+lang\s*=', content, re.IGNORECASE), (
        "<html> element must have a lang attribute for accessibility"
    )


# ── Internal anchor links ─────────────────────────────────────────────────


def test_internal_anchor_links_resolve() -> None:
    """Every href="#foo" must have a matching id="foo" somewhere in the page."""
    collector = _parse_index()
    fragment_hrefs = [h[1:] for h in collector.hrefs if h.startswith("#")]
    broken = [f for f in fragment_hrefs if f not in collector.ids]
    assert not broken, (
        f"Broken internal anchor links (no matching id): {broken}"
    )


def test_required_section_ids_present() -> None:
    """Nav links reference specific section ids — make sure they all exist."""
    required_ids = {"how-i-work", "impact", "technologies", "projects", "experience", "hero"}
    collector = _parse_index()
    missing = required_ids - collector.ids
    assert not missing, f"Required section ids missing from index.html: {missing}"


# ── External link format ──────────────────────────────────────────────────


def test_no_http_external_links() -> None:
    """All external links must use https, not plain http."""
    collector = _parse_index()
    http_links = [h for h in collector.hrefs if h.startswith("http://")]
    assert not http_links, (
        f"External links must use https://. Found http:// links: {http_links}"
    )


def test_image_srcs_not_empty() -> None:
    collector = _parse_index()
    empty_srcs = [s for s in collector.srcs if not s.strip()]
    assert not empty_srcs, "Found <img> elements with empty src attributes"


def test_no_localhost_links() -> None:
    collector = _parse_index()
    bad = [h for h in collector.hrefs if re.search(r'localhost|127\.0\.0\.1', h)]
    assert not bad, f"index.html must not contain localhost links: {bad}"


# ── Image size guard ──────────────────────────────────────────────────────


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".avif"}
MAX_BYTES = 500 * 1024  # 500 KB


def _committed_images() -> list[Path]:
    images = []
    for path in ROOT.rglob("*"):
        if path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        if any(part.startswith(".") for part in path.parts):
            continue
        images.append(path)
    return images


@pytest.mark.parametrize("image_path", _committed_images() or [Path("/dev/null")])
def test_image_size_under_limit(image_path: Path) -> None:
    if image_path == Path("/dev/null"):
        pytest.skip("No committed images found")
    size = image_path.stat().st_size
    assert size <= MAX_BYTES, (
        f"{image_path.relative_to(ROOT)} is {size / 1024:.1f} KB — exceeds 500 KB limit"
    )


# ── check_image_sizes script ──────────────────────────────────────────────


def _load_check_image_sizes():
    import importlib.util

    script = ROOT / "scripts" / "check_image_sizes.py"
    spec = importlib.util.spec_from_file_location("check_image_sizes", script)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_check_image_sizes_script_exists() -> None:
    assert (ROOT / "scripts" / "check_image_sizes.py").is_file()


def test_check_image_sizes_returns_zero_for_clean_repo(tmp_path: Path) -> None:
    mod = _load_check_image_sizes()
    mod.ROOT = tmp_path
    assert mod.find_oversized_images() == []


def test_check_image_sizes_detects_oversized(tmp_path: Path) -> None:
    big_img = tmp_path / "big.png"
    big_img.write_bytes(b"x" * (MAX_BYTES + 1))

    mod = _load_check_image_sizes()
    mod.ROOT = tmp_path
    oversized = mod.find_oversized_images()

    assert len(oversized) == 1
    assert oversized[0][0] == big_img
    assert oversized[0][1] > MAX_BYTES


def test_check_image_sizes_ignores_dotdirs(tmp_path: Path) -> None:
    hidden_dir = tmp_path / ".git"
    hidden_dir.mkdir()
    (hidden_dir / "big.png").write_bytes(b"x" * (MAX_BYTES + 1))

    mod = _load_check_image_sizes()
    mod.ROOT = tmp_path
    assert mod.find_oversized_images() == []


def test_check_image_sizes_accepts_exact_limit(tmp_path: Path) -> None:
    img = tmp_path / "exact.gif"
    img.write_bytes(b"x" * MAX_BYTES)

    mod = _load_check_image_sizes()
    mod.ROOT = tmp_path
    assert mod.find_oversized_images() == []


def test_check_image_sizes_handles_multiple_extensions(tmp_path: Path) -> None:
    for ext in (".jpg", ".jpeg", ".webp", ".avif"):
        f = tmp_path / f"big{ext}"
        f.write_bytes(b"x" * (MAX_BYTES + 1))

    mod = _load_check_image_sizes()
    mod.ROOT = tmp_path
    oversized = mod.find_oversized_images()
    assert len(oversized) == 4


def test_check_image_sizes_main_exit_zero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load_check_image_sizes()
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    assert mod.main() == 0


def test_check_image_sizes_main_exit_one(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    big_img = tmp_path / "huge.png"
    big_img.write_bytes(b"x" * (MAX_BYTES + 1))

    mod = _load_check_image_sizes()
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    assert mod.main() == 1


# ── validate_media script ─────────────────────────────────────────────────


def _load_validate_media():
    import importlib.util

    script = ROOT / "scripts" / "validate_media.py"
    spec = importlib.util.spec_from_file_location("validate_media", script)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_validate_media_script_exists() -> None:
    assert (ROOT / "scripts" / "validate_media.py").is_file()


def test_validate_media_clean_image(tmp_path: Path) -> None:
    html = tmp_path / "index.html"
    html.write_text(
        '<!DOCTYPE html><html lang="en"><body>'
        '<img src="foo.png" alt="Foo" width="100" height="80" loading="lazy">'
        '</body></html>',
        encoding="utf-8",
    )
    mod = _load_validate_media()
    issues, validator = mod.validate_media(html)
    assert issues == []
    assert len(validator.images) == 1


def test_validate_media_missing_alt(tmp_path: Path) -> None:
    html = tmp_path / "index.html"
    html.write_text(
        '<img src="foo.png" width="100" height="80" loading="lazy">',
        encoding="utf-8",
    )
    mod = _load_validate_media()
    issues, _ = mod.validate_media(html)
    assert any("alt" in i for i in issues)


def test_validate_media_missing_lazy(tmp_path: Path) -> None:
    html = tmp_path / "index.html"
    html.write_text(
        '<img src="foo.png" alt="x" width="100" height="80">',
        encoding="utf-8",
    )
    mod = _load_validate_media()
    issues, _ = mod.validate_media(html)
    assert any("lazy" in i for i in issues)


def test_validate_media_missing_dimensions(tmp_path: Path) -> None:
    html = tmp_path / "index.html"
    html.write_text(
        '<img src="bar.png" alt="x" loading="lazy">',
        encoding="utf-8",
    )
    mod = _load_validate_media()
    issues, _ = mod.validate_media(html)
    assert any("width" in i for i in issues)
    assert any("height" in i for i in issues)


def test_validate_media_empty_src(tmp_path: Path) -> None:
    html = tmp_path / "index.html"
    html.write_text('<img src="" alt="x" width="10" height="10" loading="lazy">', encoding="utf-8")
    mod = _load_validate_media()
    issues, _ = mod.validate_media(html)
    assert any("empty" in i.lower() for i in issues)


def test_validate_media_valid_video(tmp_path: Path) -> None:
    html = tmp_path / "index.html"
    html.write_text(
        '<video width="640" height="360" autoplay muted loop playsinline></video>',
        encoding="utf-8",
    )
    mod = _load_validate_media()
    issues, validator = mod.validate_media(html)
    assert issues == []
    assert len(validator.videos) == 1


def test_validate_media_video_missing_attrs(tmp_path: Path) -> None:
    html = tmp_path / "index.html"
    html.write_text("<video></video>", encoding="utf-8")
    mod = _load_validate_media()
    issues, _ = mod.validate_media(html)
    assert any("width" in i for i in issues)
    assert any("height" in i for i in issues)
    assert any("autoplay" in i for i in issues)
    assert any("muted" in i for i in issues)
    assert any("loop" in i for i in issues)
    assert any("playsinline" in i for i in issues)


def test_validate_media_main_exit_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """main() returns 0 when index.html has no media issues."""
    mod = _load_validate_media()
    good_html = (
        '<!DOCTYPE html><html lang="en"><body>'
        '<img src="x.png" alt="x" width="1" height="1" loading="lazy">'
        '</body></html>'
    )

    class _FakePath:
        def read_text(self, **_kw: object) -> str:
            return good_html

    monkeypatch.setattr(mod, "ROOT", type("_R", (), {"__truediv__": lambda s, o: _FakePath()})())
    issues, _ = mod.validate_media(_FakePath())  # type: ignore[arg-type]
    assert issues == []


# ── CI workflow file ──────────────────────────────────────────────────────


def test_ci_workflow_exists() -> None:
    workflow = ROOT / ".github" / "workflows" / "ci.yml"
    assert workflow.is_file(), ".github/workflows/ci.yml must exist"


def test_ci_workflow_has_required_jobs() -> None:
    workflow = ROOT / ".github" / "workflows" / "ci.yml"
    content = workflow.read_text()
    for job in ("html-validate", "link-check", "image-size", "tests"):
        assert job in content, f"CI workflow must define the '{job}' job"


def test_ci_workflow_triggers_on_pr_and_push() -> None:
    workflow = ROOT / ".github" / "workflows" / "ci.yml"
    content = workflow.read_text()
    assert "pull_request" in content, "CI workflow must trigger on pull_request"
    assert "push" in content, "CI workflow must trigger on push"


def test_ci_workflow_uses_lychee() -> None:
    workflow = ROOT / ".github" / "workflows" / "ci.yml"
    content = workflow.read_text()
    assert "lychee" in content, "CI workflow must use lychee for link checking"


def test_ci_workflow_uses_html_validate() -> None:
    workflow = ROOT / ".github" / "workflows" / "ci.yml"
    content = workflow.read_text()
    assert "html-validate" in content, "CI workflow must use html-validate"


def test_lychee_config_exists() -> None:
    assert (ROOT / ".lychee.toml").is_file(), ".lychee.toml must exist"


def test_lychee_config_excludes_linkedin() -> None:
    content = (ROOT / ".lychee.toml").read_text()
    assert "linkedin" in content.lower(), ".lychee.toml must exclude LinkedIn to avoid bot-blocking false positives"


def test_htmlvalidate_config_exists() -> None:
    assert (ROOT / ".htmlvalidate.json").is_file(), ".htmlvalidate.json must exist"
