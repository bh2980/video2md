"""Tests for the STT slice (mlx-whisper transcription, mocked Hub + model)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest

from video2md import stt as stt_mod
from video2md.errors import WhisperError


@pytest.fixture
def fake_hub(monkeypatch, tmp_path):
    """Stands in for huggingface_hub.snapshot_download; records calls."""
    import huggingface_hub

    hub_dir = tmp_path / "hub" / "models--fake"
    hub_dir.mkdir(parents=True)

    state = SimpleNamespace(
        calls=[],
        local_dir=hub_dir,
        fail_local=False,
        fail_network=False,
        offline_error=OSError("offline"),
    )

    def fake_snapshot_download(**kwargs):
        state.calls.append(kwargs)
        if kwargs.get("local_files_only") and state.fail_local:
            raise FileNotFoundError("not cached")
        if not kwargs.get("local_files_only") and state.fail_network:
            raise state.offline_error
        return str(state.local_dir)

    monkeypatch.setattr(
        huggingface_hub, "snapshot_download", fake_snapshot_download, raising=True
    )
    return state


@pytest.fixture
def fake_mlx_whisper(monkeypatch):
    """Insert a fake `mlx_whisper` module recording transcribe kwargs."""
    module = ModuleType("mlx_whisper")
    calls: list[dict] = []

    def fake_transcribe(path, **kwargs):
        calls.append({"path": path, **kwargs})
        return {
            "language": "en",
            "segments": [
                {"start": 0.0, "end": 2.5, "text": "  Hello world.  "},
                {"start": 2.5, "end": 4.0, "text": "   "},  # blank -> dropped
                {"start": 4.0, "end": 7.25, "text": "Second cue."},
            ],
        }

    module.transcribe = fake_transcribe
    monkeypatch.setitem(sys.modules, "mlx_whisper", module)
    return module, calls


MODEL_DIR = Path("/fake/models--mlx-community--whisper-tiny-mlx/snapshots/abc")


def test_transcribe_passes_local_dir_not_hub_id(fake_mlx_whisper):
    module, calls = fake_mlx_whisper
    cues, lang = stt_mod.transcribe_wav(
        Path("audio.wav"), model_dir=MODEL_DIR, language=None
    )
    assert len(calls) == 1
    assert calls[0]["path_or_hf_repo"] == str(MODEL_DIR)
    assert not calls[0]["path_or_hf_repo"].startswith("mlx-community/")
    assert Path(calls[0]["path_or_hf_repo"]).is_absolute() or "::" not in calls[0][
        "path_or_hf_repo"
    ]


def test_language_omitted_when_none(fake_mlx_whisper):
    module, calls = fake_mlx_whisper
    stt_mod.transcribe_wav(Path("audio.wav"), model_dir=MODEL_DIR, language=None)
    assert "language" not in calls[0]


def test_language_passed_when_given(fake_mlx_whisper):
    module, calls = fake_mlx_whisper
    stt_mod.transcribe_wav(Path("audio.wav"), model_dir=MODEL_DIR, language="en")
    assert calls[0]["language"] == "en"


def test_transcribe_maps_cues_and_language(fake_mlx_whisper):
    cues, lang = stt_mod.transcribe_wav(
        Path("audio.wav"), model_dir=MODEL_DIR, language=None
    )
    assert lang == "en"
    assert [c.text for c in cues] == ["Hello world.", "Second cue."]
    assert cues[0].start_s == 0.0 and cues[0].end_s == 2.5
    assert cues[1].start_s == 4.0 and cues[1].end_s == 7.25


def test_transcribe_exception_wrapped_as_whisper_error(monkeypatch):
    module = ModuleType("mlx_whisper")

    def boom(path, **kwargs):
        raise RuntimeError("model exploded")

    module.transcribe = boom
    monkeypatch.setitem(sys.modules, "mlx_whisper", module)
    with pytest.raises(WhisperError, match="model exploded"):
        stt_mod.transcribe_wav(Path("audio.wav"), model_dir=MODEL_DIR, language=None)


def test_json_default_handles_numpy_scalar():
    payload = {"score": np.float32(0.5), "count": np.int64(7)}
    dumped = json.dumps(payload, default=stt_mod.json_default)
    assert json.loads(dumped) == {"score": 0.5, "count": 7}


def test_json_default_rejects_unknown():
    with pytest.raises(TypeError):
        json.dumps({"x": object()}, default=stt_mod.json_default)


def test_resolve_model_dir_tries_local_first(fake_hub):
    fake_hub.fail_local = False
    got = stt_mod.resolve_model_dir("mlx-community/whisper-tiny-mlx", "deadbeef")
    assert got == fake_hub.local_dir
    assert len(fake_hub.calls) == 1
    assert fake_hub.calls[0]["local_files_only"] is True


def test_resolve_model_dir_falls_back_to_network(fake_hub):
    fake_hub.fail_local = True
    got = stt_mod.resolve_model_dir("mlx-community/whisper-tiny-mlx", "deadbeef")
    assert got == fake_hub.local_dir
    assert [c.get("local_files_only") for c in fake_hub.calls] == [True, False]


def test_resolve_model_dir_wraps_download_failure(fake_hub):
    fake_hub.fail_local = True
    fake_hub.fail_network = True
    with pytest.raises(WhisperError, match="Check network"):
        stt_mod.resolve_model_dir("mlx-community/whisper-tiny-mlx", "deadbeef")
    # the pinned repo id, and only it, was attempted
    assert all(
        c["repo_id"] == "mlx-community/whisper-tiny-mlx" for c in fake_hub.calls
    )


def test_turbo_not_downloaded(fake_hub):
    """Guard: this slice must never touch the turbo model weights."""
    fake_hub.fail_local = True
    fake_hub.fail_network = True
    # even if asked, only the exact pinned repo passed in is used
    with pytest.raises(WhisperError):
        stt_mod.resolve_model_dir("mlx-community/whisper-tiny-mlx", "deadbeef")
    repos = {c["repo_id"] for c in fake_hub.calls}
    assert repos == {"mlx-community/whisper-tiny-mlx"}
    assert all("turbo" not in c["repo_id"] for c in fake_hub.calls)
