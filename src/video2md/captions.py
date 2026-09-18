from __future__ import annotations

from pathlib import Path

import webvtt

from video2md.errors import CaptionParseError
from video2md.models import SpeechCue

_EXTENSIONS = (".vtt", ".srt")


def timestamp_to_seconds(ts) -> float:
    return ts.hours * 3600 + ts.minutes * 60 + ts.seconds + ts.milliseconds / 1000.0


def discover(video: Path) -> Path | None:
    """Find a sibling captions file: same stem, .vtt before .srt, case-insensitive."""
    for ext in _EXTENSIONS:
        for candidate in (video.with_suffix(ext), video.with_suffix(ext.upper())):
            if candidate.is_file():
                return candidate
    return None


def load(path: Path) -> list[SpeechCue]:
    try:
        if path.suffix.lower() == ".vtt":
            captions = webvtt.read(str(path))
        elif path.suffix.lower() == ".srt":
            captions = webvtt.from_srt(str(path))
        else:
            raise CaptionParseError(f"Unsupported captions extension: {path}")
    except (webvtt.errors.MalformedCaptionError, webvtt.errors.MalformedFileError) as exc:
        raise CaptionParseError(f"Failed to parse captions file: {path}: {exc}") from exc

    cues: list[SpeechCue] = []
    for caption in captions:
        lines = [" ".join(line.split()) for line in caption.lines]
        text = "\n".join(lines).strip()
        if not text:
            continue
        cues.append(
            SpeechCue(
                start_s=timestamp_to_seconds(caption.start_time),
                end_s=timestamp_to_seconds(caption.end_time),
                text=text,
            )
        )
    return cues
