"""Pipeline orchestration: stage order, work-dir cache, overlap, Markdown write."""

from __future__ import annotations

import importlib.metadata
import json
import logging
import os
import shutil
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from video2md.cache import (
    CACHE_FAILED,
    CACHE_MISSING,
    CACHE_REMOVED,
    CACHE_SKIPPED_OUTSIDE_ROOT,
    CACHE_SKIPPED_OUTPUT,
    fingerprint,
    load_manifest,
    read_json,
    remove_work_cache,
    save_manifest,
    write_json,
)
from video2md.config import (
    FRAME_SCALE_MAX,
    OCR_FRAMEWORK,
    WHISPER_ALIASES,
    WHISPER_REVISIONS,
    ocr_language_preference,
)
from video2md.errors import FfmpegError, InputNotFoundError
from video2md.models import (
    LectureDocument,
    Options,
    ScreenBlock,
    SpeechCue,
    ToolVersions,
    VideoProbe,
)
from video2md import captions, ffmpeg, frames, ocr, stt

logger = logging.getLogger(__name__)

_NO_STREAM_SNIPPET = "Output file does not contain any stream"
_IMPORTLIB_NAMES = {
    "webvtt_py": "webvtt-py",
    "mlx_whisper": "mlx-whisper",
    "ocrmac": "ocrmac",
    "imagehash": "ImageHash",
}


def _probe_from_json(data: dict, path: Path) -> VideoProbe:
    return VideoProbe(
        path=Path(data["path"]),
        duration_s=float(data["duration_s"]),
        width=int(data["width"]),
        height=int(data["height"]),
        has_audio=bool(data["has_audio"]),
        audio_codec=data.get("audio_codec"),
        video_codec=data.get("video_codec"),
        fps=data.get("fps"),
        size_bytes=int(data["size_bytes"]),
    )


def _cue_from_json(data: dict) -> SpeechCue:
    return SpeechCue(
        start_s=float(data["start_s"]),
        end_s=float(data["end_s"]),
        text=str(data["text"]),
    )


def _warn(message: str) -> None:
    print(f"video2md: warning: {message}", file=sys.stderr)
    logger.warning(message)


def _captions_file(opts: Options) -> Path | None:
    if opts.force_stt:
        return None
    if opts.captions is not None:
        return opts.captions
    return captions.discover(opts.video)


def run(opts: Options) -> Path:
    video = opts.video.resolve()
    work = opts.work_dir
    work.mkdir(parents=True, exist_ok=True)

    manifest: dict = {} if opts.force else load_manifest(work)
    timings: dict[str, float] = {}
    warnings: list[str] = []

    def timed(stage: str, fn):
        t0 = time.monotonic()
        result = fn()
        timings[stage] = round(time.monotonic() - t0, 3)
        save_manifest(work, {**manifest, "stage_timings_s": {**timings}})
        return result

    # ---- Probe ----------------------------------------------------------
    def do_probe() -> VideoProbe:
        cached = read_json(work / "probe.json")
        if cached is not None and not opts.force:
            return _probe_from_json(cached, video)
        try:
            probe = ffmpeg.probe(video)
        except InputNotFoundError:
            raise
        write_json(work / "probe.json", {
            "path": str(probe.path),
            "duration_s": probe.duration_s,
            "width": probe.width,
            "height": probe.height,
            "has_audio": probe.has_audio,
            "audio_codec": probe.audio_codec,
            "video_codec": probe.video_codec,
            "fps": probe.fps,
            "size_bytes": probe.size_bytes,
        })
        manifest.setdefault("stages", {})["probe"] = "ok"
        return probe

    probe = timed("probe", do_probe)

    # ---- Fingerprints ---------------------------------------------------
    captions_path = None if opts.skip_speech else _captions_file(opts)
    if captions_path is not None and not captions_path.exists():
        raise InputNotFoundError(f"input not found: {captions_path}")

    if opts.whisper_model in WHISPER_ALIASES:
        resolved_repo = WHISPER_ALIASES[opts.whisper_model]
        pinned_sha = WHISPER_REVISIONS[resolved_repo]
        local_model_dir: Path | None = None
    else:
        resolved_repo = opts.whisper_model
        pinned_sha = ""
        model_path = Path(opts.whisper_model)
        local_model_dir = model_path if model_path.is_dir() else None

    speech_fp = fingerprint({
        "captions_path": str(captions_path.resolve()) if captions_path else "",
        "captions_mtime_ns": captions_path.stat().st_mtime_ns if captions_path else 0,
        "force_stt": opts.force_stt,
        "skip_speech": opts.skip_speech,
        "has_audio": probe.has_audio,
        "whisper_repo": resolved_repo,
        "whisper_revision": pinned_sha,
        "whisper_model_mtime_ns": (
            local_model_dir.stat().st_mtime_ns if local_model_dir is not None else 0
        ),
        "cache_schema": 1,
        "language": opts.language or "",
    })
    frames_fp = fingerprint({
        "scene_threshold": opts.scene_threshold,
        "min_scene_interval": opts.min_scene_interval,
        "max_frames": opts.max_frames,
        "hash_threshold": opts.hash_threshold,
        "frame_every": opts.frame_every,
        "frame_scale_max": FRAME_SCALE_MAX,
        "cache_schema": 1,
    })
    ocr_fp = fingerprint({
        "frames_fp": frames_fp,
        "ocr_confidence": opts.ocr_confidence,
        "ocr_min_chars": opts.ocr_min_chars,
        "language": opts.language or "",
        "ocr_framework": OCR_FRAMEWORK,
        "ocr_languages": ocr_language_preference(opts.language),
        "cache_schema": 1,
    })

    # Fingerprints go into the manifest up front so every per-stage save
    # records them. `prev` keeps what was loaded from disk for fp matching.
    prev = manifest
    manifest = {
        **manifest,
        "video": str(video),
        "size_bytes": probe.size_bytes,
        "speech_fp": speech_fp,
        "frames_fp": frames_fp,
        "ocr_fp": ocr_fp,
    }
    save_manifest(work, manifest)

    # ---- Speech ---------------------------------------------------------
    stages: dict = manifest.setdefault("stages", {})
    speech_source = "none"
    cues: list[SpeechCue] = []
    whisper_detected: str | None = None

    def do_speech() -> None:
        nonlocal speech_source, cues, whisper_detected
        if opts.skip_speech:
            speech_source = "none"
            warnings.append("skip-speech")
            return

        if (
            not opts.force
            and prev.get("speech_fp") == speech_fp
            and stages.get("speech") == "captions"
            and captions_path is not None
            and read_json(work / "captions.json") is not None
        ):
            cached = read_json(work / "captions.json")
            if isinstance(cached, list):
                cues = [_cue_from_json(d) for d in cached]
                speech_source = "captions"
                stages["speech"] = "captions"
                return

        if (
            not opts.force
            and prev.get("speech_fp") == speech_fp
            and stages.get("speech") == "whisper"
            and captions_path is None
            and read_json(work / "whisper.json") is not None
        ):
            cached = read_json(work / "whisper.json")
            if isinstance(cached, list):
                cues = [_cue_from_json(d) for d in cached]
                speech_source = "whisper"
                stages["speech"] = "whisper"
                return

        if captions_path is not None:
            cues = captions.load(captions_path)
            write_json(work / "captions.json", [c.__dict__ for c in cues])
            speech_source = "captions"
            stages["speech"] = "captions"
            return

        if not probe.has_audio:
            _warn("no audio stream; writing OCR-only markdown")
            warnings.append("no audio stream")
            speech_source = "none"
            stages["speech"] = "none"
            return

        wav = work / "audio.wav"
        try:
            ffmpeg.extract_audio(probe.path, wav)
        except FfmpegError as e:
            if _NO_STREAM_SNIPPET in (e.args[0] if e.args else ""):
                _warn("no audio stream; writing OCR-only markdown")
                warnings.append("no audio stream")
                speech_source = "none"
                stages["speech"] = "none"
                return
            raise

        if local_model_dir is not None:
            model_dir = local_model_dir
        else:
            model_dir = stt.resolve_model_dir(resolved_repo, pinned_sha)
        cues, detected = stt.transcribe_wav(wav, model_dir=model_dir, language=opts.language)
        write_json(work / "whisper.json", [c.__dict__ for c in cues])
        whisper_detected = detected or None
        speech_source = "whisper"
        stages["speech"] = "whisper"

    # ---- Frames ---------------------------------------------------------
    kept_frames: list[tuple[float, Path, str]] = []

    def do_frames() -> None:
        if (
            not opts.force
            and prev.get("frames_fp") == frames_fp
            and stages.get("frames") == "ok"
            and read_json(work / "frames.json") is not None
        ):
            cached = read_json(work / "frames.json")
            if isinstance(cached, list):
                for row in cached:
                    kept_frames.append(
                        (float(row["t"]), Path(row["path"]), str(row["phash"]))
                    )
                stages["frames"] = "ok"
                return

        scene = ffmpeg.extract_scene_frames(
            probe.path, work / "frames", threshold=opts.scene_threshold
        )
        periodic: list[tuple[float, Path]] = []
        if opts.frame_every > 0:
            periodic = ffmpeg.extract_interval_frames(
                probe.path, work / "frames_periodic", every_s=opts.frame_every
            )
        merged = frames.merge_frame_candidates(scene, periodic)
        kept, cap_warning = frames.extract_and_dedup(
            merged,
            min_scene_interval=opts.min_scene_interval,
            hash_threshold=opts.hash_threshold,
            max_frames=opts.max_frames,
        )
        kept_frames.extend(kept)
        if cap_warning:
            warnings.append(cap_warning)
        write_json(
            work / "frames.json",
            [{"t": t, "path": str(p), "phash": h} for t, p, h in kept_frames],
        )
        stages["frames"] = "ok"

    # ---- Speech + (possibly overlapped) frame extraction -----------------
    needs_speech = not opts.skip_speech
    stt_needed = needs_speech and captions_path is None and probe.has_audio
    overlap_frame_extract = stt_needed and not opts.skip_ocr
    frames_thread = None
    if overlap_frame_extract:
        # ffmpeg scene extraction is a subprocess; overlap it with Whisper.
        frames_thread = threading.Thread(target=do_frames, name="frame-extract")
        frames_thread.start()
        try:
            timed("speech", do_speech)
        finally:
            if frames_thread is not None:
                frames_thread.join()
    else:
        timed("speech", do_speech)
        if not opts.skip_ocr:
            timed("frames", do_frames)

    # ---- OCR (never overlaps Whisper) ------------------------------------
    screens: list[ScreenBlock] = []
    if not opts.skip_ocr:
        def do_ocr() -> None:
            nonlocal screens
            if (
                not opts.force
                and prev.get("ocr_fp") == ocr_fp
                and prev.get("frames_fp") == frames_fp
                and stages.get("ocr") == "ok"
                and stages.get("frames") == "ok"
                and read_json(work / "ocr.json") is not None
            ):
                cached = read_json(work / "ocr.json")
                if isinstance(cached, list):
                    screens = _blocks_from_json(cached)
                    stages["ocr"] = "ok"
                    return
            screens = ocr.run_frames(
                kept_frames,
                language=opts.language,
                confidence=opts.ocr_confidence,
                min_chars=opts.ocr_min_chars,
            )
            if not screens:
                _warn("OCR produced no text blocks")
                warnings.append("OCR produced no text blocks")
            write_json(
                work / "ocr.json",
                [
                    {
                        "t": b.t_s,
                        "path": str(b.frame_path),
                        "phash": b.phash,
                        "lines": [
                            {"text": l.text, "confidence": l.confidence,
                             "bbox": list(l.bbox)}
                            for l in b.lines
                        ],
                    }
                    for b in screens
                ],
            )
            stages["ocr"] = "ok"

        timed("ocr", do_ocr)
        _copy_kept_frames(opts, kept_frames, screens)

    # ---- Document + Markdown ---------------------------------------------
    now = datetime.now(timezone.utc).replace(microsecond=0)

    def dist_version(distro: str) -> str | None:
        try:
            return importlib.metadata.version(distro)
        except importlib.metadata.PackageNotFoundError:
            return None

    tool = ToolVersions(
        name="video2md",
        video2md=dist_version("video2md") or "0.0.0",
        ffmpeg=ffmpeg.ffmpeg_version(),
        mlx_whisper=dist_version(_IMPORTLIB_NAMES["mlx_whisper"]),
        ocrmac=dist_version(_IMPORTLIB_NAMES["ocrmac"]),
        webvtt_py=dist_version(_IMPORTLIB_NAMES["webvtt_py"]),
        imagehash=dist_version(_IMPORTLIB_NAMES["imagehash"]),
    )

    language = opts.language or whisper_detected

    doc = LectureDocument(
        source=probe.path,
        probe=probe,
        source_size_bytes=probe.size_bytes,
        speech_source=speech_source,
        captions_path=captions_path if speech_source == "captions" else None,
        language=language,
        whisper_model=resolved_repo if speech_source == "whisper" else None,
        whisper_revision=pinned_sha or None if speech_source == "whisper" else None,
        generated_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        tool=tool,
        cues=cues,
        screens=screens,
        source_sha256=_hash_source(opts) if opts.hash_source else None,
        warnings=warnings,
    )

    from video2md.markdown import render

    text = render(doc, md_path=opts.out)
    out = opts.out
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(text, "utf-8")
    os.replace(tmp, out)

    sidecar = out.parent / f"{out.stem}.transcript.json"
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    payload = [
        {"start_s": c.start_s, "end_s": c.end_s, "text": c.text} for c in cues
    ]
    sidecar_tmp = sidecar.with_name(sidecar.name + ".tmp")
    sidecar_tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", "utf-8"
    )
    os.replace(sidecar_tmp, sidecar)

    # manifest has already been rewritten after each stage via `timed`
    save_manifest(work, manifest)

    _cleanup_work_cache(opts, work)
    return out


def _cleanup_work_cache(opts: Options, work: Path) -> None:
    """Post-success work-cache lifecycle.

    - Default: delete the per-video work cache (WAV, temp frames, OCR/STT
      results) now that final outputs are written. Final artifacts
      (.md, .transcript.json, .frames/) are never touched.
    - --keep-cache: keep the cache even on success (debugging / regeneration);
      takes precedence over --clean.
    - --clean: explicit cleanup, kept for compatibility; also allowed to
      remove a --work-dir override outside the managed cache root.
    - Cleanup failures only warn; they never fail a successful conversion.
    """
    if opts.keep_cache:
        return
    final_outputs = [
        opts.out,
        opts.out.parent / f"{opts.out.stem}.transcript.json",
        opts.out.parent / f"{opts.out.stem}.frames",
    ]
    status = remove_work_cache(work, outputs=final_outputs)
    if status in (CACHE_REMOVED, CACHE_MISSING):
        return
    if status == CACHE_SKIPPED_OUTSIDE_ROOT and not opts.clean:
        # --work-dir override outside ~/Library/Caches/video2md: keep it unless
        # the user explicitly asked for cleanup with --clean.
        return
    if status == CACHE_SKIPPED_OUTSIDE_ROOT:
        # --clean on an override dir outside the cache root: legacy behavior
        # was an unconditional rmtree of the work dir; keep that, still never
        # touching final outputs.
        try:
            resolved = work.resolve()
            for out in final_outputs:
                out_resolved = out.resolve()
                try:
                    out_resolved.relative_to(resolved)
                except ValueError:
                    continue
                _warn(
                    f"skipping cache cleanup; {resolved} overlaps final output "
                    f"{out_resolved}"
                )
                return
            shutil.rmtree(resolved, ignore_errors=True)
        except OSError:
            pass
        return
    if status == CACHE_SKIPPED_OUTPUT:
        _warn("skipping cache cleanup; work dir overlaps final outputs")
        return
    _warn("failed to remove work cache; continuing (conversion already succeeded)")


def _copy_kept_frames(
    opts: Options,
    kept_frames: list[tuple[float, Path, str]],
    screens: list[ScreenBlock],
) -> None:
    """Persist kept frames beside the markdown and point screens at the copies."""
    if opts.skip_ocr:
        return
    frames_out = opts.out.parent / f"{opts.out.stem}.frames"
    if frames_out.exists():
        shutil.rmtree(frames_out)
    frames_out.mkdir(parents=True)

    lines_by_t = {round(b.t_s, 3): b for b in screens}
    new_screens: list[ScreenBlock] = []
    for i, (t, src, phash) in enumerate(sorted(kept_frames, key=lambda k: k[0]), 1):
        dest = frames_out / f"{i:04d}_t{t:.3f}.jpg"
        shutil.copy2(src, dest)
        ocr_block = lines_by_t.get(round(t, 3))
        new_screens.append(
            ScreenBlock(
                t_s=t,
                frame_path=dest,
                lines=ocr_block.lines if ocr_block is not None else (),
                phash=phash,
            )
        )
    screens[:] = new_screens


def _blocks_from_json(rows: list) -> list[ScreenBlock]:
    from video2md.models import OcrLine

    blocks: list[ScreenBlock] = []
    for row in rows:
        lines = tuple(
            OcrLine(
                text=str(l["text"]),
                confidence=float(l["confidence"]),
                bbox=tuple(float(x) for x in l["bbox"]),
            )
            for l in row.get("lines", [])
        )
        blocks.append(
            ScreenBlock(
                t_s=float(row["t"]),
                frame_path=Path(row["path"]),
                lines=lines,
                phash=str(row["phash"]),
            )
        )
    return blocks


def _hash_source(opts: Options) -> str | None:
    import hashlib

    digest = hashlib.sha256()
    with open(opts.video, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()
