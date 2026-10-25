"""Offline contracts for the optional downloader; no account or media requests."""

import sys
from types import SimpleNamespace

import pytest

from youtube3 import download
from youtube3.cli import main


VIDEO_ID = "BaW_jenozKc"
URL = f"https://www.youtube.com/watch?v={VIDEO_ID}"


@pytest.mark.parametrize("value", [VIDEO_ID, URL, f"https://youtu.be/{VIDEO_ID}?t=10",
                                   URL + "&list=PLexample"])
def test_video_selection_is_always_one_canonical_youtube_url(value):
    assert download.video_url(value) == URL


@pytest.mark.parametrize("value", ["bad", "https://example.com/watch?v=" + VIDEO_ID,
                                   "https://youtube.com/playlist?list=PLexample",
                                   "file:///tmp/video", "https://youtube.com.evil/watch?v=" + VIDEO_ID])
def test_invalid_selection_is_rejected(value):
    with pytest.raises(ValueError):
        download.video_url(value)


def test_dry_run_needs_no_extra_or_oauth_and_creates_no_folder(tmp_path, monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "yt_dlp", None)
    destination = tmp_path / "media"
    monkeypatch.setattr(sys, "argv", ["youtube3", "download", "video", VIDEO_ID,
                                     "--output", str(destination), "--dry-run"])

    main.main()

    assert "Dry run" in capsys.readouterr().out
    assert not destination.exists()


def test_missing_extra_has_install_instructions(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "yt_dlp", None)
    with pytest.raises(download.DownloadError, match=r'pip install "youtube3\[download\]"'):
        download.download_video(VIDEO_ID, tmp_path)


def test_quality_output_and_single_video_reach_backend(tmp_path, monkeypatch):
    calls = []

    class FakeDownloader:
        def __init__(self, options):
            self.options = options

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def download(self, urls):
            calls.append((self.options, urls))
            return 0

    backend = SimpleNamespace(YoutubeDL=FakeDownloader, utils=SimpleNamespace(DownloadError=RuntimeError))
    monkeypatch.setitem(sys.modules, "yt_dlp", backend)

    download.download_video(URL + "&list=PLexample", tmp_path, quality=720)

    options, urls = calls.pop()
    assert urls == [URL]
    assert options["noplaylist"] is True
    assert options["paths"]["home"] == str(tmp_path)
    assert "[height<=720]" in options["format"]
    assert "%(id)s" in options["outtmpl"]
    assert options["overwrites"] is False


@pytest.mark.parametrize("quality", [0, -1])
def test_invalid_quality_is_rejected_before_loading_backend(tmp_path, quality):
    with pytest.raises(ValueError, match="positive"):
        download.download_video(VIDEO_ID, tmp_path, quality=quality)


def test_backend_failure_is_a_cli_error(tmp_path, monkeypatch, capsys):
    def fail(*args, **kwargs):
        raise download.DownloadError("Video unavailable")

    monkeypatch.setattr(download, "download_video", fail)
    monkeypatch.setattr(sys, "argv", ["youtube3", "download", "video", VIDEO_ID,
                                     "--output", str(tmp_path)])
    with pytest.raises(SystemExit) as error:
        main.main()
    assert error.value.code != 0
    assert "Video unavailable" in capsys.readouterr().err


@pytest.mark.parametrize("mode", ["exception", "status"])
def test_backend_failure_is_not_reported_as_success(tmp_path, monkeypatch, mode):
    class FailingDownloader:
        def __init__(self, options):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def download(self, urls):
            if mode == "exception":
                raise RuntimeError("Unavailable")
            return 1

    backend = SimpleNamespace(YoutubeDL=FailingDownloader, utils=SimpleNamespace(DownloadError=RuntimeError))
    monkeypatch.setitem(sys.modules, "yt_dlp", backend)
    with pytest.raises(download.DownloadError):
        download.download_video(VIDEO_ID, tmp_path)
