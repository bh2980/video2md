from __future__ import annotations

from pathlib import Path

from video2md.markdown import (
    CAPTIONS_ABSENT_SENTENCE,
    NO_AUDIO_SENTENCE,
    SKIP_SPEECH_SENTENCE,
    render,
)
from video2md.models import (
    LectureDocument,
    OcrLine,
    ScreenBlock,
    SpeechCue,
    ToolVersions,
    VideoProbe,
)


def _out(cues: list[SpeechCue], screens: list[ScreenBlock]) -> str:
    probe = _probe(duration_s=120.0)
    return render(
        LectureDocument(
            source=Path("/Users/you/Lectures/lecture.mp4"),
            probe=probe,
            source_size_bytes=1,
            speech_source="captions",
            captions_path=None,
            language=None,
            whisper_model=None,
            whisper_revision=None,
            generated_at="2026-09-17T16:02:11Z",
            tool=_tool(),
            cues=cues,
            screens=screens,
        )
    )

FIXTURE = Path(__file__).parent / "fixtures" / "expected_lecture.md"


def _probe(duration_s: float = 61.04) -> VideoProbe:
    return VideoProbe(
        path=Path("/Users/you/Lectures/cs161-binsearch.mp4"),
        duration_s=duration_s,
        width=1920,
        height=1080,
        has_audio=True,
        audio_codec="aac",
        video_codec="h264",
        fps=30.0,
        size_bytes=84_215_552,
    )


def _tool() -> ToolVersions:
    return ToolVersions(
        name="video2md",
        video2md="0.1.0",
        ffmpeg="9.0.1",
        mlx_whisper="0.4.3",
        ocrmac="1.0.1",
        webvtt_py="0.5.1",
        imagehash="4.3.2",
    )


def _ocr(*lines: str) -> tuple[OcrLine, ...]:
    return tuple(OcrLine(text=t, confidence=95.0, bbox=(0.0, 0.0, 1.0, 1.0)) for t in lines)


def _gold_document() -> LectureDocument:
    cues = [
        SpeechCue(
            1.2, 6.4,
            "Welcome back. Today we will prove the log n bound for binary search and then implement it.",
        ),
        SpeechCue(
            6.4, 12.05,
            "The invariant is that the target, if it exists, always lies in the half-open interval lo to hi.",
        ),
        SpeechCue(
            13.0, 22.8,
            "Here is the Python. Notice we use a half-open interval so we never have to "
            "special-case an empty slice. mid is floor of lo plus hi over two.",
        ),
        SpeechCue(
            23.1, 34.5,
            "Each iteration discards at least half of the remaining range, so the loop runs at "
            "most floor of log2 of n plus one times. That is the entire proof.",
        ),
        SpeechCue(
            36.0, 47.25,
            "Two caveats. The array must already be sorted, and if you overflow lo plus hi in a "
            "language with fixed-width integers, use lo plus the difference over two.",
        ),
        SpeechCue(
            48.0, 60.5,
            "Next time we will use this as a subroutine in a lower-bound argument. That is it for today.",
        ),
    ]
    screens = [
        ScreenBlock(0.0, Path("cs161-binsearch.frames/0001_t0.000.jpg"), _ocr("CS 161 — Lecture 4", "Binary Search", "Prof. Kim"), "a" * 16),
        ScreenBlock(
            12.480,
            Path("cs161-binsearch.frames/0002_t12.480.jpg"),
            _ocr(
                "def binary_search(a, x):",
                "    lo, hi = 0, len(a)",
                "    while lo < hi:",
                "        mid = (lo + hi) // 2",
                "        if a[mid] < x:",
                "            lo = mid + 1",
                "        else:",
                "            hi = mid",
                "    return lo if lo < len(a) and a[lo] == x else -1",
            ),
            "b" * 16,
        ),
        ScreenBlock(35.2, Path("cs161-binsearch.frames/0003_t35.200.jpg"), _ocr("Complexity", "Time:  O(log n)", "Space: O(1)", "Requires a sorted array"), "c" * 16),
    ]
    return LectureDocument(
        source=Path("/Users/you/Lectures/cs161-binsearch.mp4"),
        probe=_probe(),
        source_size_bytes=84_215_552,
        speech_source="captions",
        captions_path=Path("/Users/you/Lectures/cs161-binsearch.vtt"),
        language=None,
        whisper_model=None,
        whisper_revision=None,
        generated_at="2026-09-17T16:02:11Z",
        tool=_tool(),
        cues=cues,
        screens=screens,
        source_sha256=None,
        warnings=[],
    )


def test_gold_document_matches_fixture_byte_for_byte() -> None:
    gold = FIXTURE.read_text(encoding="utf-8")
    assert render(_gold_document()) == gold


def test_duration_two_fractional_digits() -> None:
    doc = _gold_document()
    doc.probe = _probe(duration_s=61.0)
    assert "duration_s: 61.00" in render(doc)


def test_backtick_ocr_line_uses_four_backtick_fence() -> None:
    doc = _gold_document()
    doc.screens = [
        ScreenBlock(0.0, Path("f.png"), _ocr("before", "```", "after"), "d" * 16),
    ]
    out = render(doc)
    assert "![](<f.png>)" in out
    assert "````text\nbefore\n```\nafter\n````" in out


def test_image_src_with_spaces_uses_angle_brackets_not_bare_parens() -> None:
    doc = _gold_document()
    rel = "01 - lecture.frames/korean_slide.jpg"
    doc.screens = [
        ScreenBlock(0.0, Path(rel), _ocr("slide"), "d" * 16),
    ]
    out = render(doc)
    assert f"![](<{rel}>)" in out
    assert f"![]({rel})" not in out


def test_empty_timeline_still_valid() -> None:
    doc = _gold_document()
    doc.cues = []
    doc.screens = []
    out = render(doc)
    assert out.startswith("---\n")
    assert out.endswith("\n")
    assert not out.endswith("\n\n")
    assert "cue_count: 0" in out
    assert "screen_count: 0" in out
    assert CAPTIONS_ABSENT_SENTENCE in out
    assert "--skip-speech" not in out


def test_skip_speech_sentence() -> None:
    doc = _gold_document()
    doc.cues = []
    doc.warnings = ["skip-speech"]
    assert SKIP_SPEECH_SENTENCE in render(doc)


def test_no_audio_stream_sentence() -> None:
    doc = _gold_document()
    doc.cues = []
    doc.warnings = ["no audio stream"]
    assert NO_AUDIO_SENTENCE in render(doc)


def test_render_uses_timeline_merge_order() -> None:
    # Screen at 12.480 must appear BEFORE the speech starting at 13.000,
    # proving ordering keeps speech after its governing screen frame.
    # The two cues (13.0–22.8 and 23.1–34.5) merge into ONE Speech section
    # whose end is the last cue's end (34.500), not 22.800.
    out = render(_gold_document())
    screen_idx = out.index("### [00:00:12.480] Screen")
    speech_idx = out.index("### Speech [00:00:13.000 – 00:00:34.500]")
    assert screen_idx < speech_idx
    # And the first event is the screen at t=0.
    assert out.index("## Timeline\n\n### [00:00:00.000] Screen") == out.index("## Timeline")


def _screen(t: float, text: str = "slide") -> ScreenBlock:
    return ScreenBlock(
        t_s=t,
        frame_path=Path(f"lecture.frames/f_{t}.jpg"),
        lines=(OcrLine(text=text, confidence=95.0, bbox=(0.0, 0.0, 1.0, 1.0)),),
        phash="a" * 16,
    )


def test_render_groups_cues_under_frames() -> None:
    cues = [
        SpeechCue(11.2, 14.5, "First we create the client."),
        SpeechCue(15.0, 18.3, "Then we send the request."),
        SpeechCue(21.0, 24.0, "Now let's handle the response."),
    ]
    out = _out(cues, [_screen(10.0), _screen(20.0)])

    ten = out.index("### [00:00:10.000] Screen")
    speech1 = out.index("### Speech [00:00:11.200 – 00:00:18.300]")
    twenty = out.index("### [00:00:20.000] Screen")
    speech2 = out.index("### Speech [00:00:21.000 – 00:00:24.000]")

    assert ten < speech1 < twenty < speech2
    # Two Speech headings: the first frame's two cues merge into one section.
    assert out.count("### Speech") == 2
    assert "First we create the client. Then we send the request." in out
    assert "Now let's handle the response." in out


def test_render_cue_before_first_frame_appears_after_first_screen() -> None:
    cues = [SpeechCue(5.0, 8.0, "early talk")]
    out = _out(cues, [_screen(10.0)])

    ten = out.index("### [00:00:10.000] Screen")
    speech = out.index("### Speech [00:00:05.000 – 00:00:08.000]")

    assert 0 < ten < speech


def test_render_no_screens_speech_only() -> None:
    cues = [
        SpeechCue(20.0, 22.0, "second"),
        SpeechCue(5.0, 8.0, "first"),
    ]
    out = _out(cues, [])

    assert "Screen" not in out.split("## Timeline", 1)[1]
    # All cues merge into ONE Speech section even with no screens.
    assert out.count("### Speech") == 1
    speech = out.index("### Speech [00:00:05.000 – 00:00:22.000]")
    assert "first second" in out


def test_render_spanning_cue_goes_to_starting_frame() -> None:
    # A cue that starts under frame t=435.0 but overlaps frame t=442.0 must
    # NOT be split: it renders whole under the 435 Screen.
    cues = [SpeechCue(440.0, 444.0, "spans")]
    out = _out(cues, [_screen(435.0), _screen(442.0)])

    first_screen = out.index("### [00:07:15.000] Screen")
    second_screen = out.index("### [00:07:22.000] Screen")
    speech = out.index("### Speech [00:07:20.000 – 00:07:24.000]")

    assert 0 < first_screen < speech < second_screen
    assert out.count("### Speech") == 1
    assert "spans" in out


def test_render_screens_only_no_cues() -> None:
    out = _out([], [_screen(10.0)])
    timeline = out.split("## Timeline", 1)[1]
    assert "### [00:00:10.000] Screen" in timeline
    assert "Speech" not in timeline
