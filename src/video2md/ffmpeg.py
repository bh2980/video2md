from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from video2md.config import FRAME_SCALE_MAX
from video2md.errors import FfmpegError, InputNotFoundError
from video2md.models import VideoProbe


def run(argv: list[str], *, capture: bool = True) -> subprocess.CompletedProcess[str]:
    """Never check=True. Caller classifies returncode. Always close stdin."""
    return subprocess.run(
        argv,
        check=False,
        capture_output=capture,
        text=True,
        stdin=subprocess.DEVNULL,
    )


def _ffmpeg_prefix() -> list[str]:
    return ["ffmpeg", "-hide_banner", "-y", "-nostdin"]


def probe(path: Path) -> VideoProbe:
    argv = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        "--",
        str(path),
    ]
    proc = run(argv)
    if proc.returncode != 0:
        raise InputNotFoundError(f"input not found: {path}")
    info = json.loads(proc.stdout)
    video_stream = next(
        (s for s in info.get("streams", []) if s.get("codec_type") == "video"), {}
    )
    audio_stream = next(
        (s for s in info.get("streams", []) if s.get("codec_type") == "audio"), None
    )

    fps: float | None = None
    avg_frame_rate = video_stream.get("avg_frame_rate")
    if avg_frame_rate and "/" in avg_frame_rate:
        num, den = avg_frame_rate.split("/", 1)
        if float(den) != 0:
            fps = float(num) / float(den)

    return VideoProbe(
        path=path,
        duration_s=float(info.get("format", {}).get("duration", 0.0)),
        width=int(video_stream.get("width", 0)),
        height=int(video_stream.get("height", 0)),
        has_audio=audio_stream is not None,
        audio_codec=audio_stream.get("codec_name") if audio_stream else None,
        video_codec=video_stream.get("codec_name"),
        fps=fps,
        size_bytes=path.stat().st_size,
    )


def ffmpeg_version() -> str:
    proc = run(["ffmpeg", "-version"])
    match = re.match(r"^ffmpeg version (\S+)", proc.stdout.splitlines()[0])
    return match.group(1)


def extract_audio(video: Path, wav_path: Path) -> None:
    """Extract mono 16 kHz PCM audio to wav_path. Raises FfmpegError on failure."""
    argv = [
        *_ffmpeg_prefix(),
        "-i",
        str(video),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        str(wav_path),
    ]
    proc = run(argv)
    if proc.returncode != 0:
        raise FfmpegError(f"ffmpeg audio extraction failed: {proc.stderr}")


_SCENE_RE = re.compile(r"pts_time:(?P<t>[\d.]+)")


def extract_scene_frames(
    video: Path, frames_dir: Path, *, threshold: float
) -> list[tuple[float, Path]]:
    """Extract first frame plus scene-change frames; returns ordered (pts_time, path)."""
    frames_dir.mkdir(parents=True, exist_ok=True)
    select = f"eq(n,0)+gt(scene,{threshold})"
    pattern = str(frames_dir / "%04d.jpg")
    argv = [
        *_ffmpeg_prefix(),
        "-i",
        str(video),
        "-filter:v",
        f"select='{select}',showinfo,scale='min({FRAME_SCALE_MAX},iw)':-2",
        "-fps_mode",
        "vfr",
        "-q:v",
        "2",
        pattern,
    ]
    proc = run(argv)
    if proc.returncode != 0:
        raise FfmpegError(f"ffmpeg scene frame extraction failed: {proc.stderr}")

    times = [float(m.group("t")) for m in _SCENE_RE.finditer(proc.stderr)]

    result: list[tuple[float, Path]] = []
    candidates = sorted(
        (p for p in frames_dir.glob("*.jpg") if p.stem.isdigit() and len(p.stem) == 4),
        key=lambda p: p.stem,
    )
    if len(times) != len(candidates):
        raise FfmpegError(
            f"showinfo pts_time count ({len(times)}) does not match "
            f"written jpeg count ({len(candidates)}) for {video}; "
            f"ffmpeg scene frame stage failed"
        )
    for i, (t, src) in enumerate(zip(times, candidates, strict=True), start=1):
        dest = frames_dir / f"{i:04d}_t{t:.3f}.jpg"
        src.rename(dest)
        result.append((t, dest))
    return result


def extract_interval_frames(
    video: Path, frames_dir: Path, *, every_s: float
) -> list[tuple[float, Path]]:
    """Extract one frame every every_s seconds; returns ordered (pts_time, path)."""
    if every_s <= 0:
        raise ValueError(f"every_s must be > 0, got {every_s}")
    frames_dir.mkdir(parents=True, exist_ok=True)
    pattern = str(frames_dir / "%04d.jpg")
    argv = [
        *_ffmpeg_prefix(),
        "-i",
        str(video),
        "-filter:v",
        f"fps=1/{every_s},showinfo,scale='min({FRAME_SCALE_MAX},iw)':-2",
        "-fps_mode",
        "vfr",
        "-q:v",
        "2",
        pattern,
    ]
    proc = run(argv)
    if proc.returncode != 0:
        raise FfmpegError(f"ffmpeg interval frame extraction failed: {proc.stderr}")

    times = [float(m.group("t")) for m in _SCENE_RE.finditer(proc.stderr)]

    result: list[tuple[float, Path]] = []
    candidates = sorted(
        (p for p in frames_dir.glob("*.jpg") if p.stem.isdigit() and len(p.stem) == 4),
        key=lambda p: p.stem,
    )
    if len(times) != len(candidates):
        raise FfmpegError(
            f"showinfo pts_time count ({len(times)}) does not match "
            f"written jpeg count ({len(candidates)}) for {video}; "
            f"ffmpeg interval frame stage failed"
        )
    for i, (t, src) in enumerate(zip(times, candidates, strict=True), start=1):
        dest = frames_dir / f"{i:04d}_t{t:.3f}.jpg"
        src.rename(dest)
        result.append((t, dest))
    return result
