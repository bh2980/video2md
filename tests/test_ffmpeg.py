from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

import video2md.ffmpeg as ffmpeg_mod
from video2md.errors import FfmpegError, InputNotFoundError
from video2md.ffmpeg import (
    _ffmpeg_prefix,
    extract_audio,
    extract_interval_frames,
    extract_scene_frames,
    probe,
)


def _make_video(tmp_path: Path) -> Path:
    p = tmp_path / "video.mp4"
    p.write_bytes(b"fake video bytes for stat")
    return p


class FakeCompleted(subprocess.CompletedProcess[str]):
    pass


def _fake_run(stdout: str, returncode: int = 0):
    proc = subprocess.CompletedProcess(["ffprobe"], returncode, stdout, "")
    run_calls = []

    def runner(argv, **kwargs):
        run_calls.append(argv)
        return proc

    return runner, run_calls


def test_probe_uses_ffprobe_no_stdin(tmp_path):
    path = _make_video(tmp_path)
    payload = json.dumps(
        {
            "format": {"duration": "12.5"},
            "streams": [
                {
                    "codec_type": "video",
                    "width": 1280,
                    "height": 720,
                    "codec_name": "h264",
                    "avg_frame_rate": "30/1",
                },
                {"codec_type": "audio", "codec_name": "aac"},
            ],
        }
    )
    runner, run_calls = _fake_run(payload)
    with patch.object(ffmpeg_mod, "run", runner):
        result = probe(path)

    argv = run_calls[0]
    assert argv[0] == "ffprobe"
    assert argv[0] != "ffmpeg"
    joined = " ".join(argv)
    assert "-nostdin" not in joined
    assert "-stdin" not in joined
    assert str(path) in argv


def test_probe_parses_payload(tmp_path):
    path = _make_video(tmp_path)
    payload = json.dumps(
        {
            "format": {"duration": "12.5"},
            "streams": [
                {
                    "codec_type": "video",
                    "width": 1280,
                    "height": 720,
                    "codec_name": "h264",
                    "avg_frame_rate": "30/1",
                },
                {"codec_type": "audio", "codec_name": "aac"},
            ],
        }
    )
    runner, _ = _fake_run(payload)
    with patch.object(ffmpeg_mod, "run", runner):
        result = probe(path)

    assert result.duration_s == 12.5
    assert result.width == 1280
    assert result.height == 720
    assert result.video_codec == "h264"
    assert result.has_audio is True
    assert result.audio_codec == "aac"
    assert result.fps == 30.0


def test_probe_fps_zero_den(tmp_path):
    path = _make_video(tmp_path)
    payload = json.dumps(
        {
            "format": {"duration": "1.0"},
            "streams": [
                {
                    "codec_type": "video",
                    "width": 640,
                    "height": 360,
                    "codec_name": "h264",
                    "avg_frame_rate": "0/0",
                }
            ],
        }
    )
    runner, _ = _fake_run(payload)
    with patch.object(ffmpeg_mod, "run", runner):
        result = probe(path)
    assert result.fps is None


def test_probe_nonzero_input_not_found(tmp_path):
    path = _make_video(tmp_path)
    runner, _ = _fake_run("", returncode=1)
    with patch.object(ffmpeg_mod, "run", runner), pytest.raises(InputNotFoundError):
        probe(path)


def test_probe_size_from_stat_not_json(tmp_path):
    path = _make_video(tmp_path)
    payload = json.dumps(
        {
            "format": {
                "duration": "12.5",
                "size": "999999",
                "tags": {"size": "999999"},
            },
            "streams": [
                {
                    "codec_type": "video",
                    "width": 1280,
                    "height": 720,
                    "codec_name": "h264",
                    "avg_frame_rate": "30/1",
                }
            ],
        }
    )
    runner, _ = _fake_run(payload)
    with patch.object(ffmpeg_mod, "run", runner):
        result = probe(path)
    assert result.size_bytes == path.stat().st_size
    assert result.size_bytes != 999999


def test_ffmpeg_prefix_nostdin():
    prefix = _ffmpeg_prefix()
    assert "-nostdin" in prefix
    assert "-stdin" not in prefix
    assert "false" not in prefix


def test_extract_audio_argv(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"x")
    wav = tmp_path / "audio.wav"
    runner, run_calls = _fake_run("", 0)
    with patch.object(ffmpeg_mod, "run", runner):
        extract_audio(video, wav)

    argv = run_calls[0]
    joined = " ".join(argv)
    assert "-nostdin" in joined
    assert "-stdin" not in joined
    assert " false " not in f" {joined} "
    i = argv.index("-ar")
    assert argv[i + 1] == "16000"
    assert argv[-1] == str(wav)


def test_extract_audio_nonzero_raises(tmp_path):
    video = tmp_path / "video.mp4"
    wav = tmp_path / "audio.wav"
    runner, _ = _fake_run("", 1)
    with patch.object(ffmpeg_mod, "run", runner), pytest.raises(FfmpegError):
        extract_audio(video, wav)


def _fake_scene_run(stderr: str, files: list[str] | None = None):
    calls = []

    def runner(argv, **kwargs):
        calls.append(argv)
        frames_dir = Path([a for a in argv if a.endswith("%04d.jpg")][0]).parent
        for name in files or ["0001.jpg", "0002.jpg"]:
            (frames_dir / name).write_bytes(b"jpeg")
        return subprocess.CompletedProcess(["ffmpeg"], 0, "", stderr)

    return runner, calls


def test_extract_scene_frames_argv_and_rename(tmp_path):
    video = tmp_path / "video.mp4"
    frames_dir = tmp_path / "frames"
    stderr = (
        "frame 0 pts_time:0\n"
        "frame 1 pts_time:12.48\n"
    )
    runner, calls = _fake_scene_run(stderr)
    with patch.object(ffmpeg_mod, "run", runner):
        result = extract_scene_frames(video, frames_dir, threshold=0.4)

    argv = calls[0]
    joined = " ".join(argv)
    assert "-nostdin" in joined
    assert "-fps_mode" in argv
    assert "vfr" in argv
    assert "-vsync" not in joined
    assert "-stdin" not in joined
    assert any(str(frames_dir / "%04d.jpg") in a for a in argv)

    assert [t for t, _ in result] == [0.0, 12.48]
    assert result[0][1] == frames_dir / "0001_t0.000.jpg"
    assert result[1][1] == frames_dir / "0002_t12.480.jpg"
    assert result[0][1].read_bytes()


def test_extract_scene_frames_count_mismatch_raises(tmp_path):
    video = tmp_path / "video.mp4"
    frames_dir = tmp_path / "frames"
    stderr = "frame 0 pts_time:0\n"
    runner, calls = _fake_scene_run(stderr, files=["0001.jpg", "0002.jpg"])
    with (
        patch.object(ffmpeg_mod, "run", runner),
        pytest.raises(FfmpegError, match=r"\(1\).*\(2\)"),
    ):
        extract_scene_frames(video, frames_dir, threshold=0.4)
    assert len(calls) == 1  # no retry of the same argv


def test_extract_scene_frames_nonzero_raises(tmp_path):
    video = tmp_path / "video.mp4"
    frames_dir = tmp_path / "frames"

    def runner(argv, **kwargs):
        return subprocess.CompletedProcess(["ffmpeg"], 2, "", "boom")

    with (
        patch.object(ffmpeg_mod, "run", runner),
        pytest.raises(FfmpegError),
    ):
        extract_scene_frames(video, frames_dir, threshold=0.3)


def _fake_interval_run(stderr: str, returncode: int = 0, files=None, no_files=False):
    calls = []

    def runner(argv, **kwargs):
        calls.append(argv)
        if no_files:
            return subprocess.CompletedProcess(["ffmpeg"], returncode, "", stderr)
        frames_dir = Path([a for a in argv if a.endswith("%04d.jpg")][0]).parent
        for name in files or ["0001.jpg", "0002.jpg"]:
            (frames_dir / name).write_bytes(b"jpeg")
        return subprocess.CompletedProcess(["ffmpeg"], returncode, "", stderr)

    return runner, calls


def test_extract_interval_frames_argv(tmp_path):
    video = tmp_path / "video.mp4"
    frames_dir = tmp_path / "frames_periodic"
    stderr = "frame 0 pts_time:0\nframe 1 pts_time:5\n"
    runner, calls = _fake_interval_run(stderr)
    with patch.object(ffmpeg_mod, "run", runner):
        result = extract_interval_frames(video, frames_dir, every_s=5.0)

    argv = calls[0]
    joined = " ".join(argv)
    assert argv[0] == "ffmpeg"
    assert "-hide_banner" in argv
    assert "-nostdin" in joined
    assert "-stdin" not in joined
    assert "-fps_mode" in argv
    assert "vfr" in argv
    assert "-vsync" not in joined
    i = argv.index("-filter:v")
    assert argv[i + 1] == "fps=1/5.0,showinfo,scale='min(1920,iw)':-2"
    assert any(str(frames_dir / "%04d.jpg") in a for a in argv)
    assert [t for t, _ in result] == [0.0, 5.0]
    assert result[0][1] == frames_dir / "0001_t0.000.jpg"
    assert result[1][1] == frames_dir / "0002_t5.000.jpg"


def test_extract_interval_frames_fps_int_arg_string(tmp_path):
    video = tmp_path / "video.mp4"
    frames_dir = tmp_path / "frames_periodic"
    stderr = "frame 0 pts_time:0\n"
    runner, calls = _fake_interval_run(stderr, files=["0001.jpg"])
    with patch.object(ffmpeg_mod, "run", runner):
        extract_interval_frames(video, frames_dir, every_s=5)
    joined = " ".join(calls[0])
    assert "fps=1/5" in joined


def test_extract_interval_frames_count_mismatch_raises_no_retry(tmp_path):
    video = tmp_path / "video.mp4"
    frames_dir = tmp_path / "frames_periodic"
    stderr = "frame 0 pts_time:0\n"
    runner, calls = _fake_interval_run(stderr, files=["0001.jpg", "0002.jpg"])
    with (
        patch.object(ffmpeg_mod, "run", runner),
        pytest.raises(FfmpegError, match=r"\(1\).*\(2\)"),
    ):
        extract_interval_frames(video, frames_dir, every_s=5.0)
    assert len(calls) == 1  # no retry


def test_extract_interval_frames_nonzero_raises(tmp_path):
    video = tmp_path / "video.mp4"
    frames_dir = tmp_path / "frames_periodic"
    runner, _ = _fake_interval_run("boom", returncode=2, no_files=True)
    with (
        patch.object(ffmpeg_mod, "run", runner),
        pytest.raises(FfmpegError),
    ):
        extract_interval_frames(video, frames_dir, every_s=5.0)
