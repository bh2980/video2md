from pathlib import Path

import pytest

from video2md.cli import main


def test_help_returns_zero():
    assert main(["--help"]) == 0


def test_version_returns_zero():
    assert main(["--version"]) == 0


def test_skip_ocr_and_skip_speech_together_is_usage_error(dummy_video: Path):
    assert main([str(dummy_video), "--skip-ocr", "--skip-speech"]) == 2


def test_unknown_whisper_model_is_usage_error(dummy_video: Path, capsys):
    code = main([str(dummy_video), "--whisper-model", "mlx-community/not-a-model"])
    assert code == 2
    assert "unknown --whisper-model" in capsys.readouterr().err


def test_missing_input_returns_four(capsys):
    code = main(["/nonexistent/definitely-missing.mp4"])
    assert code == 4
    assert "input not found:" in capsys.readouterr().err


def test_unreadable_captions_returns_four(dummy_video: Path, capsys):
    code = main([str(dummy_video), "--captions", "/nonexistent/captions.vtt"])
    assert code == 4
    assert "input not found: /nonexistent/captions.vtt" in capsys.readouterr().err


def test_missing_video_argument_is_usage_error():
    assert main([]) == 2


def test_valid_invocation_writes_markdown(dummy_video: Path, patched_checks, capsys, tmp_path: Path, monkeypatch):
    out = tmp_path / "out.md"

    def fake_run(opts):
        out.write_text("# hello\n")
        return out

    monkeypatch.setattr("video2md.cli.pipeline.run", fake_run)
    code = main([str(dummy_video), "--out", str(out)])
    captured = capsys.readouterr()
    assert code == 0
    assert str(out) in captured.out
    assert out.exists()


def test_valid_invocation_default_out_and_work_dir(
    dummy_video: Path, patched_checks, capsys, tmp_path: Path, monkeypatch
):
    captured_opts = {}

    def fake_run(opts):
        written = tmp_path / "video.md"
        written.write_text("# x\n")
        return written

    def fake_work_dir(video, override):
        captured_opts["video"] = Path(video)
        return tmp_path / "work"

    monkeypatch.setattr("video2md.cli.work_dir_for", fake_work_dir)
    monkeypatch.setattr("video2md.cli.pipeline.run", fake_run)
    code = main([str(dummy_video)])
    captured = capsys.readouterr()
    assert code == 0
    assert captured_opts["video"] == dummy_video
    assert str(tmp_path / "video.md") in captured.out


def test_valid_invocation_with_all_flags(
    dummy_video: Path, patched_checks, capsys, tmp_path: Path, monkeypatch
):
    out = tmp_path / "out.md"

    def fake_run(opts):
        out.write_text("# flags\n")
        return out

    monkeypatch.setattr("video2md.cli.pipeline.run", fake_run)
    code = main(
        [
            str(dummy_video),
            "--out",
            str(tmp_path / "out.md"),
            "--work-dir",
            str(tmp_path / "work"),
            "--language",
            "en",
            "--whisper-model",
            "small",
            "--scene-threshold",
            "0.35",
            "--min-scene-interval",
            "2.0",
            "--max-frames",
            "100",
            "--hash-threshold",
            "10",
            "--frame-every",
            "2.5",
            "--ocr-confidence",
            "0.4",
            "--ocr-min-chars",
            "8",
            "--force-stt",
            "--force",
            "--clean",
            "--hash-source",
            "-v",
        ]
    )
    assert code == 0
    assert str(tmp_path / "out.md") in capsys.readouterr().out


def test_frame_every_default_is_five(
    dummy_video: Path, patched_checks, capsys, tmp_path: Path, monkeypatch
):
    captured = {}

    def fake_run(opts):
        captured["opts"] = opts
        out = tmp_path / "out.md"
        out.write_text("# x\n")
        return out

    monkeypatch.setattr("video2md.cli.pipeline.run", fake_run)
    assert main([str(dummy_video)]) == 0
    assert captured["opts"].frame_every == 5.0


def test_frame_every_negative_returns_two(dummy_video: Path, capsys):
    assert main([str(dummy_video), "--frame-every", "-1"]) == 2
    assert "`--frame-every` must be >= 0" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Batch (multi-input) tests
# ---------------------------------------------------------------------------


def test_two_files_batch_succeeds(dummy_video, patched_checks, capsys, tmp_path, monkeypatch):
    """Two dummy files are turned into two jobs by expand_inputs."""

    def fake_run(opts):
        written = opts.video.with_suffix(".md")
        written.write_text("# x\n")
        return written

    runs: list[str] = []

    def counting_run(opts):
        runs.append(opts.video.name)
        return fake_run(opts)

    dummy_video.with_suffix(".mov").write_bytes(b"x")
    second = tmp_path / "b.mp4"
    second.write_bytes(b"x")
    monkeypatch.setattr("video2md.cli.pipeline.run", counting_run)
    code = main([str(dummy_video), str(second)])
    out = capsys.readouterr()
    assert code == 0
    assert "[1/2]" in out.out and "[2/2]" in out.out
    assert "Done: 2 succeeded, 0 failed" in out.out
    # progress lines exist, not just a bare md path as the only output
    out_lines = [line for line in out.out.splitlines() if line.strip()]
    assert all(line.startswith("[") or line.startswith("Done:") for line in out_lines)
    assert runs == ["video.mp4", "b.mp4"]


def test_directory_of_two_mp4s(dummy_video, patched_checks, capsys, tmp_path, monkeypatch):
    directory = tmp_path / "videos"
    directory.mkdir()
    (directory / "a.mp4").write_bytes(b"a")
    (directory / "b.mp4").write_bytes(b"b")

    runs: list[str] = []

    def fake_run(opts):
        runs.append(opts.video.name)
        written = opts.video.with_suffix(".md")
        written.write_text("# x\n")
        return written

    monkeypatch.setattr("video2md.cli.pipeline.run", fake_run)
    code = main([str(directory)])
    assert code == 0
    assert runs == ["a.mp4", "b.mp4"]


def test_recursive_vs_not_for_nested_mp4(patched_checks, capsys, tmp_path, monkeypatch):
    (tmp_path / "top.mp4").write_bytes(b"t")
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "deep.mp4").write_bytes(b"d")

    runs: list[str] = []

    def fake_run(opts):
        runs.append(opts.video.name)
        written = opts.video.with_suffix(".md")
        written.write_text("# x\n")
        return written

    monkeypatch.setattr("video2md.cli.pipeline.run", fake_run)

    code = main([str(tmp_path)])
    assert code == 0
    assert runs == ["top.mp4"]
    runs.clear()

    code = main([str(tmp_path), "--recursive"])
    assert code == 0
    assert runs == ["deep.mp4", "top.mp4"]


def test_single_job_no_done_line(dummy_video, patched_checks, capsys, monkeypatch):
    def fake_run(opts):
        written = opts.video.with_suffix(".md")
        written.write_text("# x\n")
        return written

    monkeypatch.setattr("video2md.cli.pipeline.run", fake_run)
    md = dummy_video.with_suffix(".md")
    code = main([str(dummy_video)])
    out = capsys.readouterr().out
    assert code == 0
    assert str(md) in out
    assert "Done:" not in out


def test_out_with_two_files_writes_into_directory(
    dummy_video, patched_checks, capsys, tmp_path, monkeypatch
):
    outs: list[Path] = []

    def fake_run(opts):
        outs.append(opts.out)
        opts.out.parent.mkdir(parents=True, exist_ok=True)
        opts.out.write_text("# x\n")
        return opts.out

    monkeypatch.setattr("video2md.cli.pipeline.run", fake_run)
    second = tmp_path / "b.mp4"
    second.write_bytes(b"x")
    notes = tmp_path / "notes"
    code = main([str(dummy_video), str(second), "--out", str(notes)])
    assert code == 0
    assert outs == [notes / "video.md", notes / "b.md"]


def test_single_file_in_folder_out_prints_markdown_path(
    patched_checks, capsys, tmp_path, monkeypatch
):
    lectures = tmp_path / "lectures"
    lectures.mkdir()
    (lectures / "only.mp4").write_bytes(b"x")
    notes = tmp_path / "notes"

    def fake_run(opts):
        opts.out.parent.mkdir(parents=True, exist_ok=True)
        opts.out.write_text("# x\n")
        return opts.out

    monkeypatch.setattr("video2md.cli.pipeline.run", fake_run)
    code = main([str(lectures), "--out", str(notes)])
    captured = capsys.readouterr().out
    assert code == 0
    assert str(notes / "only.md") in captured
    assert "Done:" not in captured


def test_folder_input_out_is_directory(patched_checks, capsys, tmp_path, monkeypatch):
    lectures = tmp_path / "lectures"
    lectures.mkdir()
    (lectures / "01.mp4").write_bytes(b"x")
    (lectures / "02.mp4").write_bytes(b"x")
    notes = tmp_path / "notes"
    outs: list[Path] = []

    def fake_run(opts):
        outs.append(opts.out)
        opts.out.parent.mkdir(parents=True, exist_ok=True)
        opts.out.write_text("# x\n")
        return opts.out

    monkeypatch.setattr("video2md.cli.pipeline.run", fake_run)
    code = main([str(lectures), "--out", str(notes)])
    assert code == 0
    assert outs == [notes / "01.md", notes / "02.md"]
    assert "Done: 2 succeeded, 0 failed" in capsys.readouterr().out


def test_folder_recursive_out_preserves_relative_path(
    patched_checks, capsys, tmp_path, monkeypatch
):
    lectures = tmp_path / "lectures"
    (lectures / "sub").mkdir(parents=True)
    (lectures / "top.mp4").write_bytes(b"x")
    (lectures / "sub" / "deep.mp4").write_bytes(b"x")
    notes = tmp_path / "notes"
    outs: list[Path] = []

    def fake_run(opts):
        outs.append(opts.out)
        opts.out.parent.mkdir(parents=True, exist_ok=True)
        opts.out.write_text("# x\n")
        return opts.out

    monkeypatch.setattr("video2md.cli.pipeline.run", fake_run)
    code = main([str(lectures), "--recursive", "--out", str(notes)])
    assert code == 0
    assert notes / "sub" / "deep.md" in outs
    assert notes / "top.md" in outs


def test_two_folder_inputs_out_prefixes_folder_name(
    patched_checks, capsys, tmp_path, monkeypatch
):
    week1 = tmp_path / "week1"
    week2 = tmp_path / "week2"
    week1.mkdir()
    week2.mkdir()
    (week1 / "01.mp4").write_bytes(b"x")
    (week2 / "01.mp4").write_bytes(b"x")
    notes = tmp_path / "notes"
    outs: list[Path] = []

    def fake_run(opts):
        outs.append(opts.out)
        opts.out.parent.mkdir(parents=True, exist_ok=True)
        opts.out.write_text("# x\n")
        return opts.out

    monkeypatch.setattr("video2md.cli.pipeline.run", fake_run)
    code = main([str(week1), str(week2), "--out", str(notes)])
    assert code == 0
    assert outs == [notes / "week1" / "01.md", notes / "week2" / "01.md"]


def test_folder_out_existing_file_is_usage_error(
    patched_checks, capsys, tmp_path, monkeypatch
):
    lectures = tmp_path / "lectures"
    lectures.mkdir()
    (lectures / "01.mp4").write_bytes(b"x")
    existing = tmp_path / "notes.md"
    existing.write_text("not a dir")
    called = []
    monkeypatch.setattr("video2md.cli.pipeline.run", lambda opts: called.append(opts) or opts.out)
    code = main([str(lectures), "--out", str(existing)])
    assert code == 2
    assert "must be a directory" in capsys.readouterr().err
    assert not called


def test_captions_with_two_files_is_usage_error(dummy_video, patched_checks, tmp_path, monkeypatch):
    called = []

    def fake_run(opts):
        called.append(opts)
        return opts.video.with_suffix(".md")

    monkeypatch.setattr("video2md.cli.pipeline.run", fake_run)
    second = tmp_path / "b.mp4"
    second.write_bytes(b"x")
    code = main([str(dummy_video), str(second), "--captions", str(tmp_path / "c.vtt")])
    assert code == 2
    assert not called


def test_empty_directory_no_videos_found(patched_checks, capsys, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    code = main([str(empty)])
    captured = capsys.readouterr()
    assert code == 2
    assert "no videos found" in captured.err


def test_batch_second_job_fails_continues(patched_checks, capsys, tmp_path, monkeypatch):
    from video2md.errors import WhisperError

    first = tmp_path / "a.mp4"
    second = tmp_path / "b.mp4"
    first.write_bytes(b"a")
    second.write_bytes(b"b")

    runs: list[str] = []

    def fake_run(opts):
        runs.append(opts.video.name)
        if opts.video.name == "b.mp4":
            raise WhisperError("boom")
        written = opts.video.with_suffix(".md")
        written.write_text("# x\n")
        return written

    monkeypatch.setattr("video2md.cli.pipeline.run", fake_run)
    code = main([str(first), str(second)])
    out = capsys.readouterr()
    assert runs == ["a.mp4", "b.mp4"]
    assert code == 1
    assert "FAILED (exit 5)" in out.out
    assert "Done: 1 succeeded, 1 failed" in out.out
    assert str(second) in out.out


def test_fail_fast_stops_and_returns_code(patched_checks, capsys, tmp_path, monkeypatch):
    from video2md.errors import WhisperError

    first = tmp_path / "a.mp4"
    second = tmp_path / "b.mp4"
    third = tmp_path / "c.mp4"
    for p in (first, second, third):
        p.write_bytes(b"x")

    runs: list[str] = []

    def fake_run(opts):
        runs.append(opts.video.name)
        if opts.video.name == "b.mp4":
            raise WhisperError("boom")
        written = opts.video.with_suffix(".md")
        written.write_text("# x\n")
        return written

    monkeypatch.setattr("video2md.cli.pipeline.run", fake_run)
    code = main([str(first), str(second), str(third), "--fail-fast"])
    out = capsys.readouterr()
    assert runs == ["a.mp4", "b.mp4"]
    assert code == 5
    assert "FAILED (exit 5)" in out.out
    assert "Done: 1 succeeded, 1 failed" in out.out



# ---------------------------------------------------------------------------
# --keep-cache flag plumbing
# ---------------------------------------------------------------------------


def test_keep_cache_flag_reaches_options(dummy_video, patched_checks, tmp_path, monkeypatch):
    captured = {}

    def fake_run(opts):
        captured["opts"] = opts
        out = tmp_path / "out.md"
        out.write_text("# x\n")
        return out

    monkeypatch.setattr("video2md.cli.pipeline.run", fake_run)
    assert main([str(dummy_video), "--keep-cache"]) == 0
    assert captured["opts"].keep_cache is True


def test_keep_cache_defaults_to_false(dummy_video, patched_checks, tmp_path, monkeypatch):
    captured = {}

    def fake_run(opts):
        captured["opts"] = opts
        out = tmp_path / "out.md"
        out.write_text("# x\n")
        return out

    monkeypatch.setattr("video2md.cli.pipeline.run", fake_run)
    assert main([str(dummy_video)]) == 0
    assert captured["opts"].keep_cache is False


def test_keep_cache_reaches_batch_options(dummy_video, patched_checks, tmp_path, monkeypatch):
    captured_opts = []

    def fake_run(opts):
        captured_opts.append(opts)
        written = opts.video.with_suffix(".md")
        written.write_text("# x\n")
        return written

    monkeypatch.setattr("video2md.cli.pipeline.run", fake_run)
    second = tmp_path / "b.mp4"
    second.write_bytes(b"x")
    assert main([str(dummy_video), str(second), "--keep-cache"]) == 0
    assert all(opts.keep_cache for opts in captured_opts)


def test_clean_and_keep_cache_coexist_keep_cache_wins(
    dummy_video, patched_checks, tmp_path, monkeypatch
):
    captured = {}

    def fake_run(opts):
        captured["opts"] = opts
        out = tmp_path / "out.md"
        out.write_text("# x\n")
        return out

    monkeypatch.setattr("video2md.cli.pipeline.run", fake_run)
    assert main([str(dummy_video), "--keep-cache", "--clean"]) == 0
    assert captured["opts"].keep_cache is True
    assert captured["opts"].clean is True


# ---------------------------------------------------------------------------
# `cache info` / `cache clear`
# ---------------------------------------------------------------------------


@pytest.fixture
def managed_cache(tmp_path, monkeypatch):
    """Point the CLI's managed CACHE_ROOT at a tmp dir."""
    import video2md.cache as cache_mod

    root = tmp_path / "cacheroot"
    monkeypatch.setattr(cache_mod, "CACHE_ROOT", root)
    return root


def test_cache_info_missing_root_is_success(managed_cache, capsys):
    code = main(["cache", "info"])
    out = capsys.readouterr().out
    assert code == 0
    assert f"Cache: {managed_cache}" in out
    assert "Size: 0 B" in out
    assert "Entries: 0" in out


def test_cache_info_reports_size_and_entries(managed_cache, capsys):
    a = managed_cache / "aaaa"
    a.mkdir(parents=True)
    (a / "audio.wav").write_bytes(b"x" * 1024)
    b = managed_cache / "bbbb"
    b.mkdir()
    (b / "f").write_bytes(b"y" * 1024)

    code = main(["cache", "info"])
    out = capsys.readouterr().out
    assert code == 0
    assert f"Cache: {managed_cache}" in out
    assert "Size: 2.0 KB" in out
    assert "Entries: 2" in out


def test_cache_info_no_ffmpeg_or_platform_checks_needed(managed_cache, monkeypatch):
    """Cache commands must work even when ffmpeg/platform checks would fail."""
    import video2md.cli as cli_mod

    def boom():
        raise AssertionError("must not be called")

    monkeypatch.setattr(cli_mod, "require_platform", boom)
    monkeypatch.setattr(cli_mod, "require_ffmpeg", boom)
    assert main(["cache", "info"]) == 0


def test_cache_clear_missing_root_is_success(managed_cache, capsys):
    code = main(["cache", "clear"])
    out = capsys.readouterr().out
    assert code == 0
    assert f"under {managed_cache}" in out


def test_cache_clear_removes_entries_keeps_outside_outputs(
    managed_cache, tmp_path, capsys
):
    a = managed_cache / "aaaa"
    a.mkdir(parents=True)
    (a / "audio.wav").write_bytes(b"x" * 10)
    (managed_cache / "bbbb").mkdir()

    # Final artifacts live outside the cache root and must survive.
    md = tmp_path / "lecture.md"
    md.write_text("# keep")
    frames = tmp_path / "lecture.frames"
    frames.mkdir()
    (frames / "0001.jpg").write_bytes(b"x")

    code = main(["cache", "clear"])
    out = capsys.readouterr().out
    assert code == 0
    assert "Cleared 2 entries" in out
    assert managed_cache.is_dir()  # root preserved, only entries removed
    assert list(managed_cache.iterdir()) == []
    assert md.exists()
    assert (frames / "0001.jpg").exists()


def test_cache_clear_empty_root_is_success(managed_cache, capsys):
    managed_cache.mkdir()
    code = main(["cache", "clear"])
    out = capsys.readouterr().out
    assert code == 0
    assert "Cleared 0 entries" in out


def test_cache_unknown_subcommand_is_treated_as_input(managed_cache, capsys):
    "Only info/clear are cache subcommands; anything else falls back to inputs."
    code = main(["cache", "bogus"])
    captured = capsys.readouterr()
    assert code == 1  # batch with 0/2 succeeded
    assert "input not found: bogus" in captured.err


def test_bare_cache_is_treated_as_input_not_subcommand(patched_checks, capsys):
    "A path literally named 'cache' (no info/clear) still behaves as an input."
    code = main(["cache"])
    captured = capsys.readouterr()
    assert code == 4
    assert "input not found: cache" in captured.err
