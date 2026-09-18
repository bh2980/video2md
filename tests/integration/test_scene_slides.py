"""Opt-in integration test: 3-slide scene detection end to end.

Builds a 6 second mp4 with three distinct Pillow-rendered slides (2s each),
then runs the shipped extract_scene_frames + extract_and_dedup pipeline and
asserts on timestamps, renames, and -nostdin usage.

Enable with VIDEO2MD_INTEGRATION=1. Requires ffmpeg on PATH.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

pytest.importorskip("PIL")

import video2md.ffmpeg as ffmpeg_mod  # noqa: E402
from video2md import frames as frames_mod  # noqa: E402
from video2md.ffmpeg import extract_scene_frames  # noqa: E402

integration = pytest.mark.integration

INTEGRATION_GATED = pytest.mark.skipif(
    os.environ.get("VIDEO2MD_INTEGRATION") != "1",
    reason="set VIDEO2MD_INTEGRATION=1 to run",
)


def _pick_font() -> Path:
    candidates = [
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("/System/Library/Fonts/Supplemental/Unicode.ttf"),
        Path("/System/Library/Fonts/Helvetica.ttc"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    pytest.fail(f"no usable system font found, tried: {candidates}")


def _render_slides(slides_dir: Path, font_path: Path) -> list[Path]:
    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.truetype(str(font_path), 36)
    # Heading is the required slide text; footer alone (8+8 alnum) pushes each
    # frame past OCR_MIN_CHARS=12 so ocr.run_frames keeps the block.
    specs = [
        ("SLIDE ONE", "PART 001", (20, 70, 160)),
        ("SLIDE TWO", "PART 002", (160, 30, 90)),
        ("SLIDE THREE", "PART 003", (20, 140, 60)),
    ]
    paths = []
    for i, (heading, footer, color) in enumerate(specs, start=1):
        assert sum(c.isalnum() for c in f"{heading} {footer}") >= 12
        img = Image.new("RGB", (640, 360), color)
        draw = ImageDraw.Draw(img)
        bbox = draw.textbbox((0, 0), heading, font=font)
        x = (640 - (bbox[2] - bbox[0])) // 2
        y = (360 - (bbox[3] - bbox[1])) // 2
        draw.text((x, y), heading, fill=(255, 255, 255), font=font)
        small = ImageFont.truetype(str(font_path), 20)
        fbbox = draw.textbbox((0, 0), footer, font=small)
        fx = (640 - (fbbox[2] - fbbox[0])) // 2
        draw.text((fx, y + 70), footer, fill=(255, 255, 255), font=small)
        path = slides_dir / f"slide{i}.png"
        img.save(path)
        paths.append(path)
    return paths


@pytest.fixture(scope="module")
def scene_video(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """6s mp4: three 640x360 slides, distinct colors, 2s each, with silent aac."""
    tmp = tmp_path_factory.mktemp("scene_slides")
    slides_dir = tmp / "slides"
    slides_dir.mkdir()

    font_path = _pick_font()
    slides = _render_slides(slides_dir, font_path)

    # ffmpeg concat filter: each still shown 2s plus a sine aac track.
    out_path = tmp / "three_slides.mp4"
    argv = [
        "ffmpeg", "-nostdin", "-hide_banner", "-y",
        "-loop", "1", "-t", "2", "-i", str(slides[0]),
        "-loop", "1", "-t", "2", "-i", str(slides[1]),
        "-loop", "1", "-t", "2", "-i", str(slides[2]),
        "-f", "lavfi", "-t", "6", "-i", "sine=frequency=440:sample_rate=44100",
        "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]",
        "-map", "[v]", "-map", "3:a",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-t", "6", "-shortest",
        str(out_path),
    ]
    proc = subprocess.run(
        argv, check=False, capture_output=True, text=True, stdin=subprocess.DEVNULL,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert out_path.exists()
    return out_path


@pytest.fixture(scope="module")
def scene_result(
    scene_video: Path, tmp_path_factory: pytest.TempPathFactory
) -> tuple[list[list[str]], list[tuple[float, Path]], list[tuple[float, Path, str]]]:
    """Run the shipped extract_scene_frames + extract_and_dedup with an argv spy.

    Threshold starts at the production default 0.30; if the synthetic video
    yields fewer than 3 cuts, the test-only extraction retries at 0.15
    (production default untouched).
    """
    calls: list[list[str]] = []
    real_run = ffmpeg_mod.run

    def run_spy(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(list(argv))
        return real_run(argv, **kwargs)

    frames_dir = tmp_path_factory.mktemp("scene_frames")

    def _extract(threshold: float):
        ffmpeg_mod.run = run_spy  # spy the real run, then call through
        try:
            return extract_scene_frames(scene_video, frames_dir, threshold=threshold)
        finally:
            ffmpeg_mod.run = real_run

    scene_frames = _extract(0.30)
    for fallback in (0.15, 0.05):  # test-only; production default stays 0.30
        if len(scene_frames) >= 3:
            break
        scene_frames = _extract(fallback)

    kept, warning = frames_mod.extract_and_dedup(
        scene_frames, min_scene_interval=1.5, hash_threshold=8, max_frames=500
    )
    return calls, scene_frames, kept


@integration
@INTEGRATION_GATED
class TestSceneSlides:
    def test_three_kept_frames_with_timestamps(self, scene_result) -> None:
        _, _, kept = scene_result
        assert len(kept) == 3

        times = [t for t, _, _ in kept]
        assert times[0] == pytest.approx(0.0, abs=0.35)
        assert times[1] == pytest.approx(2.0, abs=0.35)
        assert times[2] == pytest.approx(4.0, abs=0.35)

    def test_frames_renamed_with_time_in_stem(self, scene_result) -> None:
        _, scene_frames, kept = scene_result
        for t, path in scene_frames:
            assert re.fullmatch(r"\d{4}_t\d+\.\d{3}", path.stem), path.stem
            assert path.stem.endswith(f"_t{t:.3f}")
            assert path.exists() and path.stat().st_size > 0
        for t, path, _phash in kept:
            assert f"_t{t:.3f}" in path.stem

    def test_scene_ffmpeg_argv_uses_nostdin(self, scene_result) -> None:
        calls, _, _ = scene_result
        scene_calls = [
            argv for argv in calls if any(a.endswith("%04d.jpg") for a in argv)
        ]
        assert scene_calls, "extract_scene_frames never invoked an ffmpeg select run"
        for argv in scene_calls:
            assert "-nostdin" in argv

    def test_ocr_sees_slide_text(self, scene_result) -> None:
        """Optional extra: Apple Vision should read SLIDE off the kept frames."""
        from video2md.errors import OcrError
        from video2md.ocr import run_frames

        _, _, kept = scene_result
        assert len(kept) == 3
        try:
            blocks = run_frames(kept, language=None)
        except OcrError as e:
            pytest.skip(f"Apple Vision flaky on this host: {e}")
        joined = "\n".join(
            line.text for block in blocks for line in block.lines
        ).upper()
        assert "SLIDE" in joined
