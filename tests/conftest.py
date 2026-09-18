import sys
from pathlib import Path

import pytest

import video2md.cli as cli


@pytest.fixture
def dummy_video(tmp_path: Path) -> Path:
    path = tmp_path / "video.mp4"
    path.write_bytes(b"not really a video")
    return path


@pytest.fixture
def patched_checks(monkeypatch: pytest.MonkeyPatch):
    """Patch platform and ffmpeg checks so tests do not depend on the host."""
    monkeypatch.setattr(cli, "require_platform", lambda: None)
    monkeypatch.setattr(cli, "require_ffmpeg", lambda: None)


@pytest.fixture
def capsys_binary_fd(capsys):
    return sys.stderr
