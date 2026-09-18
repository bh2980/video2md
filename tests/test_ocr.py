"""Tests for the OCR slice (ocrmac-backed screen text extraction)."""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

import pytest

from video2md import ocr as ocr_mod
from video2md.errors import OcrError


# A single fake annotation, mirroring ocrmac's (text, confidence, [x, y, w, h])
# with a *list* bbox as the runtime returns.
FAKE_ANNOTATION = ("HELLO OCR TEST PAGE", 0.9, [0.1, 0.2, 0.3, 0.4])


class FakeOCR:
    def __init__(self, *args, **kwargs):
        self.k = kwargs

    def recognize(self):
        return [FAKE_ANNOTATION]


@pytest.fixture
def fake_ocrmac(monkeypatch):
    """Insert a fake `ocrmac` module so the lazy import inside
    `_vision_recognize` picks it up without the real dependency."""
    module = ModuleType("ocrmac")
    module.ocr = FakeOCR  # ocrmac.ocrmac.OCR equivalent firmware-free stand-in
    fake = ModuleType("ocrmac.ocrmac")
    fake.OCR = FakeOCR
    sys.modules["ocrmac"] = module
    sys.modules["ocrmac.ocrmac"] = fake
    monkeypatch.setattr(module, "ocrmac", fake, raising=False)
    yield fake
    sys.modules.pop("ocrmac", None)
    sys.modules.pop("ocrmac.ocrmac", None)


def test_bbox_stored_as_tuple(fake_ocrmac):
    lines = ocr_mod.recognize_frame(Path("f.png"), language=None, confidence=0.3)
    assert lines[0].text == "HELLO OCR TEST PAGE"
    assert isinstance(lines[0].bbox, tuple)
    assert not isinstance(lines[0].bbox, list)
    assert lines[0].bbox == (0.1, 0.2, 0.3, 0.4)


def test_frame_kept_when_alnum_ge_min_chars(fake_ocrmac):
    frames = [(0.0, Path("f.png"), "aa")]
    blocks = ocr_mod.run_frames(frames, language=None, confidence=0.3, min_chars=12)
    assert len(blocks) == 1
    assert blocks[0].text == "HELLO OCR TEST PAGE"  # 16 alnum chars >= 12


def test_frame_skipped_when_alnum_lt_min_chars(fake_ocrmac):
    short = ("HI", 0.9, [0.1, 0.2, 0.3, 0.4])

    class ShortOCR(FakeOCR):
        def recognize(self):
            return [short]

    ocrmac = sys.modules["ocrmac"]
    ocrmac.ocrmac.OCR = ShortOCR
    frames = [(0.0, Path("f.png"), "aa")]
    blocks = ocr_mod.run_frames(frames, language=None, confidence=0.3, min_chars=12)
    assert blocks == []


def test_empty_annotations_skipped(fake_ocrmac):
    class EmptyOCR(FakeOCR):
        def recognize(self):
            return []

    ocrmac = sys.modules["ocrmac"]
    ocrmac.ocrmac.OCR = EmptyOCR
    blocks = ocr_mod.run_frames(
        [(0.0, Path("f.png"), "aa")], language=None, confidence=0.3, min_chars=1
    )
    assert blocks == []


def test_line_order_top_to_bottom(fake_ocrmac):
    # Vision y is bottom-origin: higher (y + h) means closer to the top.
    top = ("TOP", 0.9, [0.0, 0.7, 0.5, 0.2])   # y+h = 0.9 -> first
    mid = ("MID", 0.9, [0.4, 0.4, 0.4, 0.2])   # y+h = 0.6 -> second
    low = ("LOW", 0.9, [0.0, 0.1, 0.5, 0.2])   # y+h = 0.3 -> last
    ocrmac = sys.modules["ocrmac"]
    ocrmac.ocrmac.OCR = lambda *args, **kwargs: type(
        "R", (), {"recognize": staticmethod(lambda: [low, top, mid])}
    )()
    lines = ocr_mod.recognize_frame(Path("f.png"), language=None, confidence=0.0)
    assert [ln.text for ln in lines] == ["TOP", "MID", "LOW"]


def test_left_to_right_tiebreak(fake_ocrmac):
    a = ("A", 0.9, [0.5, 0.2, 0.3, 0.3])  # same y+h as b, larger x
    b = ("B", 0.9, [0.1, 0.1, 0.4, 0.4])
    ocrmac = sys.modules["ocrmac"]
    ocrmac.ocrmac.OCR = lambda *args, **kwargs: type(
        "R", (), {"recognize": staticmethod(lambda: [a, b])}
    )()
    lines = ocr_mod.recognize_frame(Path("f.png"), language=None, confidence=0.0)
    assert [ln.text for ln in lines] == ["B", "A"]


def test_language_preference_passed(fake_ocrmac, monkeypatch):
    captured: dict = {}

    def fake_recognize(path, **kwargs):
        captured.update(kwargs)
        return [FAKE_ANNOTATION]

    monkeypatch.setattr(ocr_mod, "_vision_recognize", fake_recognize)
    ocr_mod.recognize_frame(Path("f.png"), language=None, confidence=0.3)
    assert captured["language_preference"] == ["ko-KR", "en-US"]
    assert captured["framework"] == "vision"
    assert captured["recognition_level"] == "accurate"

    ocr_mod.recognize_frame(Path("f.png"), language="de", confidence=0.3)
    assert captured["language_preference"] == ["de-DE", "ko-KR", "en-US"]

    ocr_mod.recognize_frame(Path("f.png"), language="ru", confidence=0.3)
    assert captured["language_preference"] == ["ko-KR", "en-US"]


def test_value_error_falls_back_then_raises(monkeypatch):
    calls: list = []

    def flaky(path, **kwargs):
        calls.append(kwargs.get("language_preference"))
        if kwargs.get("language_preference") is not None:
            raise ValueError("unsupported language")
        return [FAKE_ANNOTATION]

    monkeypatch.setattr(ocr_mod, "_vision_recognize", flaky)
    lines = ocr_mod.recognize_frame(Path("f.png"), language="xx", confidence=0.3)
    assert [ln.text for ln in lines] == ["HELLO OCR TEST PAGE"]
    assert calls[0] == ["ko-KR", "en-US"]
    assert calls[1] is None

    def always_bad(path, **kwargs):
        raise ValueError("bad")

    monkeypatch.setattr(ocr_mod, "_vision_recognize", always_bad)
    with pytest.raises(OcrError, match="bad"):
        ocr_mod.recognize_frame(Path("f.png"), language=None, confidence=0.3)


def test_other_exception_wrapped_as_ocr_error(monkeypatch):
    def boom(path, **kwargs):
        raise RuntimeError("vision crashed")

    monkeypatch.setattr(ocr_mod, "_vision_recognize", boom)
    with pytest.raises(OcrError, match="vision crashed"):
        ocr_mod.recognize_frame(Path("f.png"), language=None, confidence=0.3)


def test_ocr_module_does_not_import_mlx_whisper():
    assert "mlx_whisper" not in sys.modules
    assert "mlx_whisper" not in Path(ocr_mod.__file__).read_text()
    assert "mlx_whisper" not in Path(ocr_mod.__file__).name
