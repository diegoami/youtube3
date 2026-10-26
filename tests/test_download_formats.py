"""Exact format settings validate and preview without network or optional tools."""

import sys

import pytest

from youtube3 import download
from youtube3.cli import main


@pytest.mark.parametrize("flags", [
    ["--format-id", "137/18"], ["--format-id", "best[height<=720]"],
    ["--format-id", "137+140+251"], ["--format-id", "../18"],
    ["--format-id", ""], ["--format-id", "137+"],
    ["--format-id", "18", "--quality", "720"],
    ["--format-id", "137+140", "--audio-only"],
])
@pytest.mark.parametrize("command", ["video", "playlist"])
def test_invalid_exact_selection_fails_before_backend_or_writes(tmp_path, monkeypatch, command, flags):
    def unexpected():
        raise AssertionError("Invalid settings must not fetch metadata")

    monkeypatch.setattr(download, "_backend", unexpected)
    monkeypatch.setattr(sys, "argv", ["youtube3", "download", command, "BaW_jenozKc",
                                     "--output", str(tmp_path / "media"), *flags])
    with pytest.raises(SystemExit) as error:
        main.main()
    assert error.value.code == 2
    assert not list(tmp_path.iterdir())


def test_exact_pair_dry_run_needs_no_backend_or_ffmpeg(tmp_path, monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "yt_dlp", None)
    monkeypatch.setattr(download.shutil, "which", lambda name: None)
    monkeypatch.setattr(sys, "argv", ["youtube3", "download", "video", "BaW_jenozKc", "--dry-run",
                                     "--output", str(tmp_path / "media"), "--format-id", "137+140"])
    main.main()
    output = capsys.readouterr().out
    assert "exact format 137+140" in output
    assert "archive-format-137+140.txt" in output
    assert not list(tmp_path.iterdir())


def test_explicit_pair_requires_tools_before_backend_or_output_creation(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "yt_dlp", None)
    monkeypatch.setattr(download.shutil, "which", lambda name: None)
    with pytest.raises(download.DownloadError, match="Merging explicit formats requires"):
        download.download_video("BaW_jenozKc", tmp_path / "media",
                                media=download.MediaOptions(format_id="137+140"))
    assert not list(tmp_path.iterdir())


def test_exact_id_quality_conflict_is_also_rejected_by_library(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "yt_dlp", None)
    with pytest.raises(ValueError, match="--format-id"):
        download.download_video("BaW_jenozKc", tmp_path, quality=720,
                                media=download.MediaOptions(format_id="18"))
    assert not list(tmp_path.iterdir())


def test_custom_archive_still_deduplicates_across_exact_choices(tmp_path, monkeypatch, capsys):
    archive = tmp_path / "shared.txt"
    archive.write_text("youtube BaW_jenozKc\n", encoding="utf-8")
    monkeypatch.setitem(sys.modules, "yt_dlp", None)
    download.download_video("BaW_jenozKc", tmp_path / "media", archive=archive,
                            media=download.MediaOptions(format_id="137+140"))
    assert "archived" in capsys.readouterr().out
    assert not (tmp_path / "media").exists()


@pytest.mark.parametrize("value", [False, ["18"], "a" * 65, "137\n", "18%"])
def test_invalid_library_format_ids(value):
    with pytest.raises(ValueError, match="Format selection"):
        download.MediaOptions(format_id=value)
