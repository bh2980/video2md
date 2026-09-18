from pathlib import Path

from video2md.models import OcrLine, ScreenBlock, SpeechCue
from video2md.timeline import group_cues_under_screens, merge


def make_block(t_s: float, tmp_path: Path, text: str = "slide text") -> ScreenBlock:
    line = OcrLine(text=text, confidence=0.95, bbox=(0.0, 0.0, 1.0, 1.0))
    frame = Path(tmp_path) / f"frame_{t_s}.png"
    return ScreenBlock(t_s=t_s, frame_path=frame, lines=(line,), phash="deadbeef")


def test_screen_before_speech_at_same_timestamp(tmp_path):
    cues = [SpeechCue(start_s=12.48, end_s=15.0, text="hello")]
    screens = [make_block(12.48, tmp_path)]

    events = merge(cues, screens)

    assert [e.kind for e in events] == ["screen", "speech"]
    assert events[0].sort_t == 12.48


def test_empty_inputs(tmp_path):
    assert merge([], []) == []


def test_speech_cues_sorted_by_start(tmp_path):
    cues = [
        SpeechCue(start_s=20.0, end_s=22.0, text="second"),
        SpeechCue(start_s=5.0, end_s=8.0, text="first"),
    ]

    events = merge(cues, [])

    assert [e.text for e in events] == ["first", "second"]
    assert all(e.kind == "speech" for e in events)


def test_screen_at_zero_first_when_mixed(tmp_path):
    cues = [
        SpeechCue(start_s=1.0, end_s=3.0, text="a"),
        SpeechCue(start_s=10.0, end_s=12.0, text="b"),
    ]
    screens = [make_block(0.0, tmp_path), make_block(11.0, tmp_path)]

    events = merge(cues, screens)

    assert [e.kind for e in events] == ["screen", "speech", "speech", "screen"]
    assert events[0].sort_t == 0.0
    assert [e.sort_t for e in events] == [0.0, 1.0, 10.0, 11.0]


def test_group_cues_under_screens_half_open_intervals(tmp_path):
    cues = [
        SpeechCue(start_s=11.2, end_s=14.5, text="first"),
        SpeechCue(start_s=15.0, end_s=18.3, text="second"),
        SpeechCue(start_s=21.0, end_s=24.0, text="third"),
    ]
    screens = [make_block(10.0, tmp_path), make_block(20.0, tmp_path)]

    groups = group_cues_under_screens(cues, screens)

    assert [s.t_s for s, _ in groups] == [10.0, 20.0]
    assert [c.text for c in groups[0][1]] == ["first", "second"]
    assert [c.text for c in groups[1][1]] == ["third"]
    # Cue timestamps are preserved, not merged.
    assert groups[0][1][0].start_s == 11.2
    assert groups[0][1][0].end_s == 14.5


def test_group_cue_starting_on_frame_boundary_belongs_to_that_frame(tmp_path):
    cues = [SpeechCue(start_s=20.0, end_s=22.0, text="on second frame")]
    screens = [make_block(10.0, tmp_path), make_block(20.0, tmp_path)]

    groups = group_cues_under_screens(cues, screens)

    assert [c.text for c in groups[1][1]] == ["on second frame"]
    assert not groups[0][1]


def test_group_cue_before_first_frame_attaches_to_first_frame(tmp_path):
    cues = [SpeechCue(start_s=5.0, end_s=8.0, text="early")]
    screens = [make_block(10.0, tmp_path), make_block(20.0, tmp_path)]

    groups = group_cues_under_screens(cues, screens)

    assert [(s.t_s, [c.text for c in cs]) for s, cs in groups] == [
        (10.0, ["early"]),
        (20.0, []),
    ]


def test_group_no_screens_speech_only(tmp_path):
    cues = [
        SpeechCue(start_s=20.0, end_s=22.0, text="second"),
        SpeechCue(start_s=5.0, end_s=8.0, text="first"),
    ]

    groups = group_cues_under_screens(cues, [])

    assert groups == [(None, sorted(cues, key=lambda c: c.start_s))]


def test_group_screens_without_cues(tmp_path):
    screens = [make_block(10.0, tmp_path), make_block(20.0, tmp_path)]

    groups = group_cues_under_screens([], screens)

    assert [s.t_s for s, cs in groups] == [10.0, 20.0]
    assert all(cs == [] for _, cs in groups)


def test_group_cue_after_last_frame_attaches_to_last(tmp_path):
    cues = [SpeechCue(start_s=99.0, end_s=100.0, text="tail")]
    screens = [make_block(10.0, tmp_path), make_block(20.0, tmp_path)]

    groups = group_cues_under_screens(cues, screens)

    assert [c.text for c in groups[-1][1]] == ["tail"]
