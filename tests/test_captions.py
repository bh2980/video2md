from pathlib import Path

from video2md.captions import discover, load
from video2md.errors import CaptionParseError

FIXTURES = Path(__file__).parent / "fixtures"


def test_load_vtt_preserves_milliseconds():
    cues = load(FIXTURES / "sample.vtt")

    assert cues[0].start_s == 1.5
    assert cues[0].end_s == 3.0
    assert cues[0].text == "hello from vtt"
    assert cues[1].start_s == 4.25


def test_load_srt_preserves_milliseconds():
    cues = load(FIXTURES / "sample.srt")

    assert cues[0].start_s == 1.5
    assert cues[0].end_s == 3.0
    assert cues[0].text == "hello from srt"


def test_load_drops_empty_cues_and_collapses_whitespace():
    cues = load(FIXTURES / "sample.vtt")

    assert all(cue.text.strip() for cue in cues)
    assert len(cues) == 2
    assert cues[1].text == "second cue\nwith spacing"


def test_load_malformed_raises(tmp_path):
    bad = tmp_path / "bad.vtt"
    bad.write_text("not a valid vtt header\n\n00:00:01.500 --> 00:00:02.000\nhello\n")

    try:
        load(bad)
    except CaptionParseError:
        pass
    else:
        raise AssertionError("expected CaptionParseError")


def test_discover_prefers_vtt_over_srt(tmp_path):
    video = tmp_path / "lecture.mp4"
    (tmp_path / "lecture.vtt").write_text("WEBVTT\n")
    (tmp_path / "lecture.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nx\n")

    assert discover(video) == tmp_path / "lecture.vtt"


def test_discover_finds_srt_when_no_vtt(tmp_path):
    video = tmp_path / "lecture.mp4"
    (tmp_path / "lecture.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nx\n")

    assert discover(video) == tmp_path / "lecture.srt"


def test_discover_returns_none_when_absent(tmp_path):
    assert discover(tmp_path / "lecture.mp4") is None


def test_discover_matches_uppercase_extensions(tmp_path):
    video = tmp_path / "lecture.mp4"
    (tmp_path / "lecture.VTT").write_text("WEBVTT\n")

    discovered = discover(video)

    assert discovered is not None
    assert discovered.stem == "lecture"
    assert discovered.suffix.lower() == ".vtt"


def test_discover_ignores_stem_variant(tmp_path):
    video = tmp_path / "lecture.mp4"
    (tmp_path / "lecture.en.vtt").write_text("WEBVTT\n")

    assert discover(video) is None
