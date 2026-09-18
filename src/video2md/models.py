from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class VideoProbe:
    path: Path
    duration_s: float
    width: int
    height: int
    has_audio: bool
    audio_codec: str | None
    video_codec: str | None
    fps: float | None
    size_bytes: int


@dataclass(frozen=True)
class SpeechCue:
    start_s: float
    end_s: float
    text: str


@dataclass(frozen=True)
class OcrLine:
    text: str
    confidence: float
    bbox: tuple[float, float, float, float]


@dataclass(frozen=True)
class ScreenBlock:
    t_s: float
    frame_path: Path
    lines: tuple[OcrLine, ...]
    phash: str

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)


@dataclass(frozen=True)
class SpeechEvent:
    start_s: float
    end_s: float
    text: str
    kind: str = "speech"
    kind_rank: int = 1

    @property
    def sort_t(self) -> float:
        return self.start_s


@dataclass(frozen=True)
class ScreenEvent:
    t_s: float
    block: ScreenBlock
    kind: str = "screen"
    kind_rank: int = 0

    @property
    def sort_t(self) -> float:
        return self.t_s


TimelineEvent = SpeechEvent | ScreenEvent


@dataclass(frozen=True)
class ToolVersions:
    name: str
    video2md: str
    ffmpeg: str
    mlx_whisper: str | None
    ocrmac: str | None
    webvtt_py: str | None
    imagehash: str | None


@dataclass
class LectureDocument:
    source: Path
    probe: VideoProbe
    source_size_bytes: int
    speech_source: str
    captions_path: Path | None
    language: str | None
    whisper_model: str | None
    whisper_revision: str | None
    generated_at: str
    tool: ToolVersions
    cues: list[SpeechCue]
    screens: list[ScreenBlock]
    source_sha256: str | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Options:
    video: Path
    out: Path
    captions: Path | None
    work_dir: Path
    language: str | None
    whisper_model: str
    scene_threshold: float
    min_scene_interval: float
    max_frames: int
    hash_threshold: int
    frame_every: float
    ocr_confidence: float
    ocr_min_chars: int
    force_stt: bool
    skip_ocr: bool
    skip_speech: bool
    force: bool
    clean: bool
    hash_source: bool
    keep_cache: bool = False
