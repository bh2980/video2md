"""Screen OCR over selected frames using ocrmac (Apple Vision).

Consumes `(t, path, phash)` frames from the frame pipeline and returns
time-stamped `ScreenBlock` records with sorted `OcrLine` entries.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from video2md.config import (
    OCR_CONFIDENCE,
    OCR_FRAMEWORK,
    OCR_MIN_CHARS,
    ocr_language_preference,
)
from video2md.errors import OcrError
from video2md.models import OcrLine, ScreenBlock


def _vision_recognize(path: Path, **kwargs: Any) -> list[tuple[str, float, list[float]]]:
    """Import ocrmac lazily so `import video2md.ocr` stays cheap."""
    from ocrmac import ocrmac

    return ocrmac.OCR(str(path), **kwargs).recognize()


def recognize_frame(
    frame_path: Path,
    *,
    language: str | None,
    confidence: float,
) -> list[OcrLine]:
    """OCR one frame into `OcrLine`s, sorted top-to-bottom, left-to-right."""
    language_preference = ocr_language_preference(language)

    # List first (required by ocrmac); None is the automatic-language fallback.
    attempts: tuple[list[str] | None, ...] = (language_preference, None)
    last_value_error: ValueError | None = None
    annotations = []
    for attempt in attempts:
        try:
            annotations = _vision_recognize(
                frame_path,
                framework=OCR_FRAMEWORK,
                recognition_level="accurate",
                language_preference=attempt,
                confidence_threshold=confidence,
                detail=True,
            )
            last_value_error = None
            break
        except ValueError as e:
            # Vision rejected the BCP-47 preference; fall back to automatic.
            last_value_error = e
        except Exception as e:  # noqa: BLE001
            raise OcrError(f"ocr failed for {frame_path}: {e}") from e
    if last_value_error is not None:
        raise OcrError(f"ocr language preference rejected for {frame_path}: {last_value_error}")

    lines: list[OcrLine] = []
    for annotation in annotations:
        try:
            text, conf, bbox = annotation
            x, y, w, h = bbox
        except (TypeError, ValueError) as e:
            raise OcrError(f"malformed ocr annotation: {annotation!r}") from e
        lines.append(OcrLine(text=text, confidence=float(conf), bbox=(float(x), float(y), float(w), float(h))))

    # Vision bbox y is bottom-origin: sort by -(y+h) then x.
    lines.sort(key=lambda line: (-(line.bbox[1] + line.bbox[3]), line.bbox[0]))
    return lines


def run_frames(
    frames: list[tuple[float, Path, str]],
    *,
    language: str | None,
    confidence: float = OCR_CONFIDENCE,
    min_chars: int = OCR_MIN_CHARS,
) -> list[ScreenBlock]:
    """OCR each frame sequentially, dropping low-information frames."""
    blocks: list[ScreenBlock] = []
    for t, path, phash in frames:
        lines = recognize_frame(path, language=language, confidence=confidence)
        text = "\n".join(line.text for line in lines)
        if not lines or sum(c.isalnum() for c in text) < min_chars:
            continue
        blocks.append(
            ScreenBlock(t_s=t, frame_path=path, lines=tuple(lines), phash=phash)
        )
    return blocks
