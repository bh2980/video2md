from __future__ import annotations

from pathlib import Path

from video2md import timeline
from video2md.models import LectureDocument, ScreenBlock, ScreenEvent, SpeechCue, SpeechEvent

_FM_KEY_ORDER = (
    "schema",
    "source",
    "source_size_bytes",
    "duration_s",
    "width",
    "height",
    "speech_source",
    "captions_path",
    "language",
    "whisper_model",
    "whisper_revision",
    "generated_at",
    "cue_count",
    "screen_count",
    "warnings",
    "tool",
    "source_sha256",
)

_TOOL_KEY_ORDER = (
    "name",
    "version",
    "ffmpeg",
    "webvtt_py",
    "mlx_whisper",
    "ocrmac",
    "imagehash",
)

SKIP_SPEECH_SENTENCE = "No speech track. --skip-speech was set."
NO_AUDIO_SENTENCE = "No speech track. Captions were absent and the file has no audio."
CAPTIONS_ABSENT_SENTENCE = "No speech track. Captions were absent."


def _yaml_str(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _yaml_duration(seconds: float) -> str:
    return f"{round(seconds, 2):.2f}"


def fmt_ts(seconds: float) -> str:
    """Format seconds as HH:MM:SS.mmm with zero-padded hours."""
    if seconds < 0:
        seconds = 0.0
    ms = int(round(seconds * 1000.0))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def _fence(text: str) -> str:
    n = 0
    for line in text.splitlines():
        run = 0
        for ch in line:
            if ch == "`":
                run += 1
                n = max(n, run)
            else:
                run = 0
    return "`" * max(3, n + 1)


def _front_matter(doc: LectureDocument) -> str:
    values: dict[str, str] = {
        "schema": _yaml_str("video2md/v1"),
        "source": _yaml_str(str(doc.source)),
        "source_size_bytes": str(doc.source_size_bytes),
        "duration_s": _yaml_duration(doc.probe.duration_s),
        "width": str(doc.probe.width),
        "height": str(doc.probe.height),
        "speech_source": _yaml_str(doc.speech_source),
        "captions_path": _yaml_str(str(doc.captions_path)) if doc.captions_path else "null",
        "language": _yaml_str(doc.language) if doc.language else "null",
        "whisper_model": _yaml_str(doc.whisper_model) if doc.whisper_model else "null",
        "whisper_revision": _yaml_str(doc.whisper_revision) if doc.whisper_revision else "null",
        "generated_at": _yaml_str(doc.generated_at),
        "cue_count": str(len(doc.cues)),
        "screen_count": str(len(doc.screens)),
        "source_sha256": _yaml_str(doc.source_sha256) if doc.source_sha256 else "null",
    }
    lines = []
    for key in _FM_KEY_ORDER:
        if key in ("warnings", "tool", "source_sha256"):
            continue
        lines.append(f"{key}: {values[key]}")
    if doc.warnings:
        lines.append("warnings:")
        for w in doc.warnings:
            lines.append(f"  - {_yaml_str(w)}")
    else:
        lines.append("warnings: []")
    t = doc.tool
    tool_values: dict[str, str] = {
        "name": _yaml_str(t.name),
        "version": _yaml_str(t.video2md),
        "ffmpeg": _yaml_str(t.ffmpeg) if t.ffmpeg else "null",
        "webvtt_py": _yaml_str(t.webvtt_py) if t.webvtt_py else "null",
        "mlx_whisper": _yaml_str(t.mlx_whisper) if t.mlx_whisper else "null",
        "ocrmac": _yaml_str(t.ocrmac) if t.ocrmac else "null",
        "imagehash": _yaml_str(t.imagehash) if t.imagehash else "null",
    }
    lines.append("tool:")
    for key in _TOOL_KEY_ORDER:
        lines.append(f"  {key}: {tool_values[key]}")
    lines.append(f"source_sha256: {values['source_sha256']}")
    return "\n".join(lines) + "\n"


def _image_rel(block: ScreenBlock, md_path: Path | None) -> str:
    """Relative image path (POSIX slashes) for a screen frame."""
    p: Path = block.frame_path
    if not p.is_absolute():
        return p.as_posix()
    if md_path is not None:
        try:
            return p.relative_to(md_path.parent).as_posix()
        except ValueError:
            pass
    if p.parent.name.endswith(".frames"):
        return f"{p.parent.name}/{p.name}"
    return p.name


def join_cues(cues: list[SpeechCue]) -> tuple[float, float, str] | None:
    """Join a group of cues into one (start, end, text) speech section.

    Start is the first cue's ``start_s``, end is the last cue's ``end_s``,
    and texts are joined in cue order with a single ASCII space. Returns
    ``None`` for an empty group.
    """
    if not cues:
        return None
    text = " ".join(c.text.strip() for c in cues)
    return cues[0].start_s, cues[-1].end_s, text


def _render_event(event: SpeechEvent | ScreenEvent, md_path: Path | None = None) -> str:
    if isinstance(event, SpeechEvent):
        header = (
            f"### Speech [{fmt_ts(event.start_s)} – {fmt_ts(event.end_s)}]\n\n{event.text}"
        )
    else:
        text = event.block.text
        fence = _fence(text)
        rel = _image_rel(event.block, md_path)
        image = f"![](<{rel}>)"
        header = (
            f"### [{fmt_ts(event.t_s)}] Screen\n\n{image}\n\n{fence}text\n{text}\n{fence}"
        )
    return header


def render(doc: LectureDocument, md_path: Path | None = None) -> str:
    """Render a LectureDocument to the frozen Markdown output (hand-rolled YAML)."""
    groups = timeline.group_cues_under_screens(doc.cues, doc.screens)

    parts: list[str] = ["---\n", _front_matter(doc), "---\n\n"]

    stem = Path(doc.source).stem
    title = stem.replace("_", " ").replace("-", " ").title()
    body = [f"# {title}", ""]

    if not doc.cues:
        warnings = doc.warnings or []
        if "skip-speech" in warnings:
            body.append(SKIP_SPEECH_SENTENCE)
        elif any("no audio stream" in w for w in warnings):
            body.append(NO_AUDIO_SENTENCE)
        else:
            body.append(CAPTIONS_ABSENT_SENTENCE)
        body.append("")

    body.append("## Timeline")
    body.append("")
    first = True
    for screen, cues_for_screen in groups:
        blocks: list[str] = []
        if screen is not None:
            blocks.append(_render_event(ScreenEvent(t_s=screen.t_s, block=screen), md_path))
        joined = join_cues(cues_for_screen)
        if joined is not None:
            start, end, text = joined
            blocks.append(_render_event(SpeechEvent(start_s=start, end_s=end, text=text)))
        for block in blocks:
            if not first:
                body.append("")
            body.append(block)
            first = False

    # Trim trailing blank lines so the file ends with exactly one newline.
    while body and body[-1] == "":
        body.pop()

    parts.append("\n".join(body))
    return "".join(parts) + "\n"
