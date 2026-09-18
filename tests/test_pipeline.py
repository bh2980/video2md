"""Tests for pipeline.run — ffmpeg, stt, ocr, and captions are all mocked."""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

import video2md.pipeline as pipeline_mod
from video2md.models import Options, OcrLine, ScreenBlock, SpeechCue, VideoProbe
from video2md.pipeline import run

SCHEMA = 'schema: "video2md/v1"'


def make_opts(tmp_path: Path, **overrides) -> Options:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake video bytes")
    defaults = dict(
        video=video,
        out=tmp_path / "out" / "video.md",
        captions=None,
        work_dir=tmp_path / "work",
        language=None,
        whisper_model="tiny",
        scene_threshold=0.30,
        min_scene_interval=1.5,
        max_frames=500,
        hash_threshold=8,
        frame_every=5.0,
        ocr_confidence=0.30,
        ocr_min_chars=12,
        force_stt=False,
        skip_ocr=False,
        skip_speech=False,
        force=False,
        clean=False,
        hash_source=False,
    )
    defaults.update(overrides)
    return Options(**defaults)


def fake_probe(tmp_path: Path, has_audio: bool) -> VideoProbe:
    video = tmp_path / "video.mp4"
    return VideoProbe(
        path=video,
        duration_s=10.0,
        width=640,
        height=360,
        has_audio=has_audio,
        audio_codec="aac" if has_audio else None,
        video_codec="h264",
        fps=30.0,
        size_bytes=video.stat().st_size,
    )


@pytest.fixture
def mocks(tmp_path, monkeypatch):
    (tmp_path / "video.mp4").write_bytes(b"fake video bytes")
    probe = fake_probe(tmp_path, has_audio=True)

    def fake_extract_scene_frames(video, out_dir, *, threshold):
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / "0001_t0.000.jpg"
        Image.new("RGB", (64, 64), "white").save(path, format="JPEG")
        return [(0.0, path)]

    def fake_extract_and_dedup(scene, **kwargs):
        return [(t, p, "deadbeef0000") for (t, p) in scene], None

    def fake_extract_audio(video, wav_path):
        wav_path.write_bytes(b"RIFFfake")

    def fake_resolve_model_dir(repo, revision):
        mdir = tmp_path / "whisper-model"
        mdir.mkdir(exist_ok=True)
        return mdir

    def fake_transcribe_wav(wav, *, model_dir, language):
        assert isinstance(model_dir, Path), f"model_dir must be a local Path: {model_dir!r}"
        assert model_dir.is_dir()
        return [SpeechCue(start_s=0.0, end_s=2.0, text="hello whisper")], "en"

    def fake_run_frames(frames, *, language, confidence, min_chars):
        return [
            ScreenBlock(
                t_s=t,
                frame_path=path,
                lines=(OcrLine(text="FIXED TEXT PAGE", confidence=0.9, bbox=(0.1, 0.1, 0.2, 0.1)),),
                phash=phash,
            )
            for (t, path, phash) in frames
        ]

    recorded = SimpleNamespace(
        extract_audio=None,
        extract_scene_frames=None,
        extract_interval_frames=None,
        resolve_model_dir=None,
        transcribe_wav=None,
        captions_load=None,
        captions_discover_result=None,
        run_frames=None,
    )

    monkeypatch.setattr(pipeline_mod.ffmpeg, "probe", lambda path: probe)
    monkeypatch.setattr(pipeline_mod.ffmpeg, "ffmpeg_version", lambda: "9.0.1")

    def wrap_extract_audio(video, wav):
        recorded.extract_audio = (video, wav)
        fake_extract_audio(video, wav)

    monkeypatch.setattr(pipeline_mod.ffmpeg, "extract_audio", wrap_extract_audio)

    def wrap_extract_scene(*args, **kw):
        recorded.extract_scene_frames = (args, kw)
        return fake_extract_scene_frames(*args, **kw)

    monkeypatch.setattr(pipeline_mod.ffmpeg, "extract_scene_frames", wrap_extract_scene)

    def wrap_extract_interval(*args, **kw):
        recorded.extract_interval_frames = (args, kw)
        return []

    monkeypatch.setattr(
        pipeline_mod.ffmpeg, "extract_interval_frames", wrap_extract_interval
    )

    def wrap_resolve(repo, rev):
        recorded.resolve_model_dir = (repo, rev)
        return fake_resolve_model_dir(repo, rev)

    monkeypatch.setattr(pipeline_mod.stt, "resolve_model_dir", wrap_resolve)

    def wrap_transcribe(wav, **kw):
        recorded.transcribe_wav = (wav, kw)
        return fake_transcribe_wav(wav, **kw)

    monkeypatch.setattr(pipeline_mod.stt, "transcribe_wav", wrap_transcribe)

    def wrap_captions_load(path):
        recorded.captions_load = path
        return [SpeechCue(start_s=0.0, end_s=2.0, text="hello captions")]

    monkeypatch.setattr(pipeline_mod.captions, "load", wrap_captions_load)

    def wrap_discover(video):
        return recorded.captions_discover_result

    monkeypatch.setattr(pipeline_mod.captions, "discover", wrap_discover)

    def wrap_run_frames(frames, **kw):
        recorded.run_frames = frames
        return fake_run_frames(frames, **kw)

    monkeypatch.setattr(pipeline_mod.ocr, "run_frames", wrap_run_frames)

    return recorded


def test_run_writes_markdown_with_schema_and_timeline(tmp_path, mocks):
    mocks.captions_discover_result = None
    opts = make_opts(tmp_path)
    out = run(opts)
    text = out.read_text("utf-8")
    assert SCHEMA in text
    assert "## Timeline" in text
    assert out.exists()
    assert out.with_name(out.name + ".tmp").exists() is False


def test_atomic_out_exists_after_run(tmp_path, mocks):
    mocks.captions_discover_result = None
    out_path = tmp_path / "nested" / "video.md"
    opts = make_opts(tmp_path, out=out_path)
    assert run(opts) == out_path
    assert out_path.is_file()


def test_captions_win_and_stt_not_called(tmp_path, mocks):
    cap = tmp_path / "video.vtt"
    cap.write_text("WEBVTT\n\n00:00:00.000 --> 00:00:02.000\nhello\n")
    mocks.captions_discover_result = cap
    opts = make_opts(tmp_path)
    run(opts)
    assert mocks.transcribe_wav is None
    assert mocks.extract_audio is None
    assert mocks.captions_load == cap
    text = opts.out.read_text("utf-8")
    assert 'speech_source: "captions"' in text
    assert 'speech_source: "whisper"' not in text


def test_stt_called_with_local_model_dir_when_no_captions(tmp_path, mocks):
    mocks.captions_discover_result = None
    opts = make_opts(tmp_path, language="en")
    run(opts)
    assert mocks.transcribe_wav is not None
    wav, kw = mocks.transcribe_wav
    assert wav == opts.work_dir / "audio.wav"
    assert isinstance(kw["model_dir"], Path)  # passed via kwargs to real fn
    assert mocks.resolve_model_dir == (
        "mlx-community/whisper-tiny-mlx",
        "6caf9c55601caafbe6508a8b0d216bdf4783c4e8",
    )
    assert 'speech_source: "whisper"' in opts.out.read_text("utf-8")


def test_local_model_dir_passed_directly_without_resolve(tmp_path, mocks):
    mocks.captions_discover_result = None
    model_dir = tmp_path / "mymodel"
    model_dir.mkdir()
    opts = make_opts(tmp_path, whisper_model=str(model_dir))
    run(opts)
    assert mocks.resolve_model_dir is None
    assert mocks.transcribe_wav is not None
    wav, kw = mocks.transcribe_wav
    assert kw["model_dir"] == model_dir
    assert 'speech_source: "whisper"' in opts.out.read_text("utf-8")


def test_local_model_dir_front_matter_uses_local_dir_path(tmp_path, mocks):
    mocks.captions_discover_result = None
    model_dir = tmp_path / "mymodel"
    model_dir.mkdir()
    opts = make_opts(tmp_path, whisper_model=str(model_dir))
    run(opts)
    text = opts.out.read_text("utf-8")
    assert f'whisper_model: "{model_dir}"' in text
    assert "whisper_revision: null" in text


def test_empty_ocr_still_writes_file(tmp_path, mocks, monkeypatch, capsys):
    mocks.captions_discover_result = None
    monkeypatch.setattr(
        pipeline_mod.ocr,
        "run_frames",
        lambda frames, **kw: [],
    )
    opts = make_opts(tmp_path)
    out = run(opts)
    assert out.is_file()
    assert "OCR produced no text blocks" in out.read_text("utf-8")
    # Frames are still persisted even when OCR produced no text.
    frames_dir = out.parent / f"{out.stem}.frames"
    assert frames_dir.is_dir()
    assert [p.name for p in sorted(frames_dir.iterdir())] == ["0001_t0.000.jpg"]


def test_frames_dir_created_and_images_embedded(tmp_path, mocks):
    mocks.captions_discover_result = None
    opts = make_opts(tmp_path)
    out = run(opts)
    frames_dir = opts.out.parent / f"{opts.out.stem}.frames"
    assert frames_dir.is_dir()
    assert (frames_dir / "0001_t0.000.jpg").is_file()
    text = out.read_text("utf-8")
    assert "![](<video.frames/0001_t0.000.jpg>)" in text
    assert 'screen_count: 1' in text


def test_frames_dir_replaced_on_rerun_no_stale_files(tmp_path, mocks):
    mocks.captions_discover_result = None
    opts = make_opts(tmp_path, keep_cache=True)
    out = run(opts)
    frames_dir = out.parent / f"{out.stem}.frames"
    stale = frames_dir / "9999_t99.900.jpg"
    stale.write_bytes(b"stale jpeg bytes")
    run(opts)  # rerun: dir must be replaced, stale file gone
    assert not stale.exists()
    assert sorted(p.name for p in frames_dir.iterdir()) == ["0001_t0.000.jpg"]
    assert "![](<video.frames/0001_t0.000.jpg>)" in out.read_text("utf-8")


def test_skip_ocr_with_stt_works(tmp_path, mocks):
    mocks.captions_discover_result = None
    opts = make_opts(tmp_path, skip_ocr=True)
    out = run(opts)
    text = out.read_text("utf-8")
    assert "## Timeline" in text
    assert "hello whisper" in text
    assert mocks.run_frames is None


def test_no_audio_warns_ocr_only(tmp_path, mocks, monkeypatch):
    no_audio = fake_probe(tmp_path, has_audio=False)
    monkeypatch.setattr(pipeline_mod.ffmpeg, "probe", lambda path: no_audio)
    mocks.captions_discover_result = None
    opts = make_opts(tmp_path)
    out = run(opts)
    text = out.read_text("utf-8")
    assert 'speech_source: "none"' in text
    assert 'language: "en-US"' not in text


def test_extract_audio_no_stream_is_no_speech(tmp_path, mocks, capsys):
    from video2md.errors import FfmpegError

    mocks.captions_discover_result = None

    def fail_extract(video, wav):
        raise FfmpegError(
            "ffmpeg audio extraction failed: Output file does not contain any stream"
        )

    no_audio = fake_probe(tmp_path, has_audio=False)
    pipeline_mod.ffmpeg.probe = lambda path: no_audio
    pipeline_mod.ffmpeg.extract_audio = fail_extract
    opts = make_opts(tmp_path)
    out = run(opts)
    text = out.read_text("utf-8")
    assert 'speech_source: "none"' in text
    assert "warning: no audio stream; writing OCR-only markdown" in capsys.readouterr().err


def test_transcript_sidecar_written_next_to_markdown(tmp_path, mocks):
    mocks.captions_discover_result = None
    opts = make_opts(tmp_path)
    out = run(opts)
    sidecar = opts.out.parent / f"{opts.out.stem}.transcript.json"
    assert sidecar.is_file()
    payload = json.loads(sidecar.read_text("utf-8"))
    assert payload == [{"start_s": 0.0, "end_s": 2.0, "text": "hello whisper"}]
    text = sidecar.read_text("utf-8")
    assert text.endswith("\n")
    assert sidecar.with_name(sidecar.name + ".tmp").exists() is False


def test_transcript_sidecar_captions_win(tmp_path, mocks):
    cap = tmp_path / "video.vtt"
    cap.write_text("WEBVTT\n\n00:00:00.000 --> 00:00:02.000\nhello\n")
    mocks.captions_discover_result = cap
    opts = make_opts(tmp_path)
    run(opts)
    sidecar = opts.out.parent / f"{opts.out.stem}.transcript.json"
    payload = json.loads(sidecar.read_text("utf-8"))
    assert payload == [{"start_s": 0.0, "end_s": 2.0, "text": "hello captions"}]


def test_transcript_sidecar_empty_on_skip_speech(tmp_path, mocks):
    mocks.captions_discover_result = None
    opts = make_opts(tmp_path, skip_speech=True)
    out = run(opts)
    sidecar = opts.out.parent / f"{opts.out.stem}.transcript.json"
    assert sidecar.is_file()
    assert json.loads(sidecar.read_text("utf-8")) == []


def test_transcript_sidecar_preserves_cue_order_not_grouped(tmp_path, mocks, monkeypatch):
    mocks.captions_discover_result = None

    def multi_cue_transcribe(wav, *, model_dir, language):
        return [
            SpeechCue(start_s=5.0, end_s=7.0, text="second"),
            SpeechCue(start_s=0.0, end_s=2.0, text="first"),
            SpeechCue(start_s=9.0, end_s=11.0, text="third"),
        ], "en"

    monkeypatch.setattr(pipeline_mod.stt, "transcribe_wav", multi_cue_transcribe)
    opts = make_opts(tmp_path)
    run(opts)
    sidecar = opts.out.parent / f"{opts.out.stem}.transcript.json"
    payload = json.loads(sidecar.read_text("utf-8"))
    assert [c["text"] for c in payload] == ["second", "first", "third"]
    assert all(set(c.keys()) == {"start_s", "end_s", "text"} for c in payload)
    # Not nested under frames: sidecar is a flat array, no "frames" key.
    assert isinstance(payload, list)


def test_transcript_sidecar_out_parent_nested(tmp_path, mocks):
    mocks.captions_discover_result = None
    out_path = tmp_path / "notes" / "foo.md"
    opts = make_opts(tmp_path, out=out_path)
    run(opts)
    sidecar = out_path.parent / f"{out_path.stem}.transcript.json"
    assert sidecar.is_file()
    assert json.loads(sidecar.read_text("utf-8")) == [
        {"start_s": 0.0, "end_s": 2.0, "text": "hello whisper"}
    ]


def test_clean_deletes_work_dir_not_sidecar(tmp_path, mocks):
    mocks.captions_discover_result = None
    opts = make_opts(tmp_path, clean=True)
    run(opts)
    sidecar = opts.out.parent / f"{opts.out.stem}.transcript.json"
    assert sidecar.is_file()
    assert not opts.work_dir.exists()


def test_clean_deletes_work_dir(tmp_path, mocks):
    mocks.captions_discover_result = None
    opts = make_opts(tmp_path, clean=True)
    work = opts.work_dir
    (work.parent / "sentinel.txt").write_text("keep me")
    run(opts)
    assert not work.exists()
    assert work.parent.exists()
    assert (work.parent / "sentinel.txt").exists()


def test_manifest_written_after_stages(tmp_path, mocks):
    import json

    mocks.captions_discover_result = None
    opts = make_opts(tmp_path, keep_cache=True)
    run(opts)
    manifest = json.loads((opts.work_dir / "manifest.json").read_text())
    assert manifest["stages"]["speech"] == "whisper"
    assert manifest["stages"]["ocr"] == "ok"
    for key in ("speech_fp", "frames_fp", "ocr_fp"):
        assert manifest[key]


def _count_transcribe(mocks, monkeypatch):
    """Wrap the fixture's transcribe mock with a call counter; returns the list."""
    import video2md.pipeline as pm

    calls: list = []
    original = pm.stt.transcribe_wav

    def counting(wav, **kw):
        calls.append((wav, kw))
        return original(wav, **kw)

    monkeypatch.setattr(pm.stt, "transcribe_wav", counting)
    return calls


def test_fingerprints_match_fingerprint_with_cache_schema(tmp_path, mocks):
    import json

    from video2md.cache import fingerprint
    from video2md.config import (
        FRAME_SCALE_MAX,
        OCR_FRAMEWORK,
        WHISPER_ALIASES,
        WHISPER_REVISIONS,
        ocr_language_preference,
    )

    mocks.captions_discover_result = None
    opts = make_opts(tmp_path, keep_cache=True)
    run(opts)
    manifest = json.loads((opts.work_dir / "manifest.json").read_text())
    repo = WHISPER_ALIASES[opts.whisper_model]

    assert manifest["speech_fp"] == fingerprint({
        "captions_path": "",
        "captions_mtime_ns": 0,
        "force_stt": False,
        "skip_speech": False,
        "has_audio": True,
        "whisper_repo": repo,
        "whisper_revision": WHISPER_REVISIONS[repo],
        "whisper_model_mtime_ns": 0,  # alias -> 0
        "cache_schema": 1,
        "language": "",
    })
    assert manifest["frames_fp"] == fingerprint({
        "scene_threshold": opts.scene_threshold,
        "min_scene_interval": opts.min_scene_interval,
        "max_frames": opts.max_frames,
        "hash_threshold": opts.hash_threshold,
        "frame_every": opts.frame_every,
        "frame_scale_max": FRAME_SCALE_MAX,
        "cache_schema": 1,
    })
    assert manifest["ocr_fp"] == fingerprint({
        "frames_fp": manifest["frames_fp"],
        "ocr_confidence": opts.ocr_confidence,
        "ocr_min_chars": opts.ocr_min_chars,
        "language": "",
        "ocr_framework": OCR_FRAMEWORK,
        "ocr_languages": ocr_language_preference(opts.language),
        "cache_schema": 1,
    })


def test_speech_fp_stable_second_run_is_cache_hit(tmp_path, mocks, monkeypatch):
    mocks.captions_discover_result = None
    opts = make_opts(tmp_path, keep_cache=True)
    calls = _count_transcribe(mocks, monkeypatch)
    run(opts)
    run(opts)  # same inputs, same work_dir
    assert len(calls) == 1  # second run reused whisper.json


def test_local_model_dir_mtime_busts_speech_cache(tmp_path, mocks, monkeypatch):
    mocks.captions_discover_result = None
    model_dir = tmp_path / "mymodel"
    model_dir.mkdir()
    opts = make_opts(tmp_path, whisper_model=str(model_dir), keep_cache=True)
    calls = _count_transcribe(mocks, monkeypatch)

    run(opts)
    run(opts)  # cache hit: no new transcribe
    assert len(calls) == 1

    # Bump the model dir's mtime -> speech_fp must change -> rerun.
    os.utime(model_dir, ns=(2_000_000_000_000_000_000, 2_000_000_000_000_000_000))
    run(opts)
    assert len(calls) == 2  # transcribe called again


def test_periodic_frames_merged_with_scene_frames(tmp_path, mocks, monkeypatch):
    mocks.captions_discover_result = None

    def fake_scene(video, frames_dir, *, threshold):
        frames_dir.mkdir(parents=True, exist_ok=True)
        scene_jpg = frames_dir / "0001_t0.000.jpg"
        Image.new("RGB", (64, 64), "white").save(scene_jpg, format="JPEG")
        return [(0.0, scene_jpg)]

    def fake_interval(video, frames_dir, *, every_s):
        frames_dir.mkdir(parents=True, exist_ok=True)
        dup = frames_dir / "0001_t0.000.jpg"
        Image.new("RGB", (64, 64), "white").save(dup, format="JPEG")
        later = frames_dir / "0002_t5.000.jpg"
        Image.new("RGB", (64, 64), "black").save(later, format="JPEG")
        return [(0.0, dup), (5.0, dup.parent / "0002_t5.000.jpg")]

    monkeypatch.setattr(pipeline_mod.ffmpeg, "extract_scene_frames", fake_scene)
    monkeypatch.setattr(pipeline_mod.ffmpeg, "extract_interval_frames", fake_interval)

    kept = []

    def fake_dedup(frames, **kw):
        kept.extend(frames)
        return [(t, p, "deadbeef0000") for (t, p) in frames], None

    monkeypatch.setattr(pipeline_mod.frames, "extract_and_dedup", fake_dedup)

    run(make_opts(tmp_path))

    times = sorted(t for t, _ in kept)
    assert times == [0.0, 5.0]
    path_t0 = next(p for t, p in kept if t == 0.0)
    assert path_t0.parent == tmp_path / "work" / "frames"
    path_t5 = next(p for t, p in kept if t == 5.0)
    assert path_t5.parent == tmp_path / "work" / "frames_periodic"


# ---------------------------------------------------------------------------
# Work-cache lifecycle: default cleanup on success / keep on failure
# ---------------------------------------------------------------------------


@pytest.fixture
def managed_cache(tmp_path, monkeypatch):
    """Point VIDEO2MD's managed CACHE_ROOT at a tmp dir and key work dirs into it."""
    import video2md.cache as cache_mod

    root = tmp_path / "managed-cache"
    root.mkdir()
    monkeypatch.setattr(cache_mod, "CACHE_ROOT", root)
    return root


def _managed_opts(tmp_path, mocks, managed_cache, **overrides) -> Options:
    from video2md.cache import cache_key

    video = tmp_path / "video.mp4"
    work = managed_cache / cache_key(video)
    return make_opts(tmp_path, work_dir=work, **overrides)


def test_success_deletes_work_cache_by_default(tmp_path, mocks, managed_cache):
    mocks.captions_discover_result = None
    opts = _managed_opts(tmp_path, mocks, managed_cache)
    run(opts)
    assert opts.out.is_file()
    assert not opts.work_dir.exists()
    # Only this video's cache is gone; the managed root stays for other videos.
    assert managed_cache.is_dir()


def test_success_keep_cache_preserves_work_cache(tmp_path, mocks, managed_cache):
    mocks.captions_discover_result = None
    opts = _managed_opts(tmp_path, mocks, managed_cache, keep_cache=True)
    run(opts)
    assert opts.out.is_file()
    assert opts.work_dir.is_dir()
    assert (opts.work_dir / "manifest.json").is_file()


def test_failure_keeps_work_cache_for_retry(tmp_path, mocks, managed_cache, monkeypatch):
    from video2md.errors import WhisperError

    mocks.captions_discover_result = None
    opts = _managed_opts(tmp_path, mocks, managed_cache)

    def failing_transcribe(wav, *, model_dir, language):
        raise WhisperError("stt boom")

    monkeypatch.setattr(pipeline_mod.stt, "transcribe_wav", failing_transcribe)
    with pytest.raises(WhisperError):
        run(opts)

    # Final outputs were never written and the cache survives for retry.
    assert not opts.out.exists()
    assert opts.work_dir.is_dir()
    assert (opts.work_dir / "audio.wav").is_file()
    assert (opts.work_dir / "probe.json").is_file()


def test_final_outputs_are_never_deleted_by_cleanup(tmp_path, mocks, managed_cache):
    mocks.captions_discover_result = None
    opts = _managed_opts(tmp_path, mocks, managed_cache)
    out = run(opts)

    assert not opts.work_dir.exists()  # cache cleaned
    # ...but every final artifact survives.
    assert out.is_file()
    sidecar = out.parent / f"{out.stem}.transcript.json"
    assert sidecar.is_file()
    frames_dir = out.parent / f"{out.stem}.frames"
    assert frames_dir.is_dir()
    assert (frames_dir / "0001_t0.000.jpg").is_file()


def test_work_dir_override_outside_cache_root_is_left_alone(
    tmp_path, mocks, managed_cache
):
    "Default lifecycle must not delete user-specified work dirs outside the cache root."
    mocks.captions_discover_result = None
    work = tmp_path / "custom-work" / "session"
    opts = make_opts(tmp_path, work_dir=work)
    run(opts)
    assert opts.out.is_file()
    assert work.is_dir()
    assert (work / "manifest.json").is_file()


def test_cleanup_failure_warns_but_run_still_succeeds(
    tmp_path, mocks, managed_cache, monkeypatch, capsys
):
    mocks.captions_discover_result = None
    opts = _managed_opts(tmp_path, mocks, managed_cache)

    def failing_rmtree(path, *a, **kw):
        raise OSError("disk busy")

    monkeypatch.setattr(pipeline_mod.shutil, "rmtree", failing_rmtree)
    out = run(opts)
    assert out.is_file()
    assert opts.work_dir.is_dir()  # cache survived because removal failed
    captured = capsys.readouterr()
    assert "failed to remove work cache" in captured.err


def test_keep_cache_and_clean_together_still_keeps(
    tmp_path, mocks, managed_cache
):
    mocks.captions_discover_result = None
    opts = _managed_opts(
        tmp_path, mocks, managed_cache, keep_cache=True, clean=True
    )
    run(opts)
    assert opts.work_dir.is_dir()
