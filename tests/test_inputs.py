"""Tests for input expansion (files and directories -> video jobs)."""

from pathlib import Path

from video2md.inputs import (
    VIDEO_SUFFIXES,
    expand_inputs,
    markdown_destination,
    uses_out_directory,
)


def test_single_file_returned_as_is(tmp_path):
    v = tmp_path / "a.mp4"
    v.touch()
    result = expand_inputs([v])
    assert result == [v]


def test_missing_file_is_still_one_job(tmp_path):
    missing = tmp_path / "nope.mp4"
    result = expand_inputs([missing])
    assert len(result) == 1
    assert not result[0].exists()


def test_directory_non_recursive_sorted_hidden_skipped(tmp_path):
    (tmp_path / "b.MP4").touch()
    (tmp_path / "a.mp4").touch()
    (tmp_path / "skip.txt").touch()
    (tmp_path / ".hidden.mp4").touch()
    result = expand_inputs([tmp_path])
    assert [p.name for p in result] == ["a.mp4", "b.MP4"]


def test_directory_non_recursive_ignores_nested(tmp_path):
    (tmp_path / "a.mp4").touch()
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.mp4").touch()
    result = expand_inputs([tmp_path])
    assert [p.name for p in result] == ["a.mp4"]


def test_recursive_includes_nested(tmp_path):
    (tmp_path / "a.mp4").touch()
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "c.mov").touch()
    result = expand_inputs([tmp_path], recursive=True)
    assert [p.name for p in result] == ["a.mp4", "c.mov"]


def test_mix_file_and_directory_preserves_user_order(tmp_path):
    standalone = tmp_path / "standalone.mp4"
    standalone.touch()
    d = tmp_path / "dir"
    d.mkdir()
    (d / "z.mp4").touch()
    (d / "a.mp4").touch()
    result = expand_inputs([standalone, d])
    assert [p.name for p in result] == ["standalone.mp4", "a.mp4", "z.mp4"]


def test_duplicate_same_file_dedup(tmp_path):
    v = tmp_path / "a.mp4"
    v.touch()
    result = expand_inputs([v, v])
    assert len(result) == 1


def test_duplicate_dir_and_file_inside_dedup(tmp_path):
    d = tmp_path / "dir"
    d.mkdir()
    inner = d / "a.mp4"
    inner.touch()
    result = expand_inputs([d, inner])
    assert len(result) == 1
    assert result[0].name == "a.mp4"


def test_mkv_and_m4v_collected(tmp_path):
    (tmp_path / "a.mkv").touch()
    (tmp_path / "b.m4v").touch()
    result = expand_inputs([tmp_path])
    assert [p.name for p in result] == ["a.mkv", "b.m4v"]


def test_empty_directory(tmp_path):
    assert expand_inputs([tmp_path]) == []


def test_video_suffixes_constant():
    assert VIDEO_SUFFIXES == {".mp4", ".mov", ".mkv", ".m4v"}


def test_uses_out_directory_for_folder_or_multiple_jobs(tmp_path):
    d = tmp_path / "lectures"
    d.mkdir()
    (d / "a.mp4").touch()
    one = tmp_path / "solo.mp4"
    one.touch()
    two = tmp_path / "other.mp4"
    two.touch()
    assert uses_out_directory([d], [d / "a.mp4"]) is True
    assert uses_out_directory([one], [one]) is False
    assert uses_out_directory([one, two], [one, two]) is True


def test_markdown_destination_single_dir_keeps_relative(tmp_path):
    lectures = tmp_path / "lectures"
    sub = lectures / "week2"
    sub.mkdir(parents=True)
    video = sub / "03.mp4"
    video.touch()
    out = tmp_path / "notes"
    dest = markdown_destination(video, out, [lectures])
    assert dest == out / "week2" / "03.md"


def test_markdown_destination_two_dirs_prefixes_name(tmp_path):
    week1 = tmp_path / "week1"
    week2 = tmp_path / "week2"
    week1.mkdir()
    week2.mkdir()
    a = week1 / "01.mp4"
    b = week2 / "01.mp4"
    a.touch()
    b.touch()
    out = tmp_path / "notes"
    assert markdown_destination(a, out, [week1, week2]) == out / "week1" / "01.md"
    assert markdown_destination(b, out, [week1, week2]) == out / "week2" / "01.md"


def test_markdown_destination_loose_file_uses_stem(tmp_path):
    video = tmp_path / "clip.mp4"
    video.touch()
    out = tmp_path / "notes"
    assert markdown_destination(video, out, [video]) == out / "clip.md"
