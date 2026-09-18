"""Speech-to-text over extracted WAV audio using mlx-whisper.

Resolves pinned (repo, revision) pairs from the Hub into local cache
directories, then transcribes with mlx-whisper. `import mlx_whisper` is
deferred to call time so `import video2md.stt` stays cheap.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from video2md.errors import WhisperError
from video2md.models import SpeechCue


def resolve_model_dir(repo: str, revision: str) -> Path:
    """Return the local cache directory for a pinned (repo, revision).

    Prefers the existing cache (local_files_only=True) and only falls
    back to a network download when the snapshot is not cached yet.
    """
    from huggingface_hub import snapshot_download

    kwargs = {"repo_id": repo, "revision": revision}
    try:
        return Path(snapshot_download(**kwargs, local_files_only=True))
    except Exception:
        try:
            return Path(snapshot_download(**kwargs, local_files_only=False))
        except Exception as e:
            raise WhisperError(
                f"failed to download {repo}@{revision} into HF cache "
                f"({os.environ.get('HF_HOME', '~/.cache/huggingface')}). Check network."
            ) from e


def transcribe_wav(
    wav: Path,
    *,
    model_dir: Path,
    language: str | None,
) -> tuple[list[SpeechCue], str]:
    """Transcribe one WAV file into `SpeechCue`s plus the detected language."""
    try:
        import mlx_whisper
    except Exception as e:
        raise WhisperError(f"mlx-whisper unavailable: {e}") from e

    kwargs: dict[str, Any] = {
        "path_or_hf_repo": str(model_dir),  # LOCAL directory, never a Hub id
        "verbose": False,
        "word_timestamps": False,
    }
    if language is not None:
        kwargs["language"] = language  # omit key entirely when None

    try:
        result = mlx_whisper.transcribe(str(wav), **kwargs)
    except WhisperError:
        raise
    except Exception as e:
        raise WhisperError(f"transcription failed for {wav}: {e}") from e

    cues: list[SpeechCue] = []
    for segment in result.get("segments", []):
        text = segment.get("text", "")
        if not isinstance(text, str):
            continue
        text = text.strip()
        if not text:
            continue
        cues.append(
            SpeechCue(
                start_s=float(segment.get("start", 0.0)),
                end_s=float(segment.get("end", 0.0)),
                text=text,
            )
        )
    detected = result.get("language") or ""
    return cues, str(detected)


def json_default(o: Any) -> Any:
    """JSON serializer for NumPy scalars (for the later cache slice)."""
    if hasattr(o, "item"):
        return o.item()
    raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")
