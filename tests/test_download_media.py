"""Media options and format inspection without external requests."""

import sys
from types import SimpleNamespace

import pytest

from youtube3 import download
from youtube3.cli import main


VIDEO = "BaW_jenozKc"
PLAYLIST = "PL0123456789abcdef"


@pytest.fixture
def backend(monkeypatch):
    calls = []

    class FakeDownloader:
        def __init__(self, options):
            self.options = options
            calls.append(("options", options))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def download(self, urls):
            calls.append(("download", urls))
            return 0

        def extract_info(self, url, *, download, **kwargs):
            calls.append(("extract", url, download))
            if "playlist?" in url:
                return {"_type": "playlist", "entries": [{"id": VIDEO, "title": "Example"}]}
            return {"id": VIDEO, "formats": [{
                "format_id": "140", "ext": "m4a", "vcodec": "none", "acodec": "aac",
                "filesize_approx": 1048576, "url": "https://example.invalid/media",
            }]}

    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(
        YoutubeDL=FakeDownloader, utils=SimpleNamespace(DownloadError=RuntimeError),
    ))
    return calls


def test_native_audio_has_no_video_or_conversion_and_uses_separate_archive(tmp_path, backend):
    media = download.MediaOptions(audio_only=True)
    # A completed video must not suppress a later audio download.
    (tmp_path / ".youtube3-download-archive.txt").write_text(f"youtube {VIDEO}\n", encoding="utf-8")

    download.download_video(VIDEO, tmp_path, media=media)

    options = backend[0][1]
    assert options["format"] == "bestaudio"
    assert "postprocessors" not in options
    assert options["download_archive"] == str(tmp_path / ".youtube3-download-archive-audio-native.txt")
    assert any(call[0] == "download" for call in backend)


def test_audio_conversion_is_configured_and_separate_from_native_archive(tmp_path, backend, monkeypatch):
    monkeypatch.setattr(download.shutil, "which", lambda name: f"/tools/{name}")
    media = download.MediaOptions(audio_only=True, audio_format="mp3")

    download.download_video(VIDEO, tmp_path, media=media)

    options = backend[0][1]
    assert options["postprocessors"] == [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}]
    assert options["download_archive"].endswith("-audio-mp3.txt")


def test_conversion_missing_ffmpeg_fails_before_backend_or_directory_creation(tmp_path, backend, monkeypatch):
    monkeypatch.setattr(download.shutil, "which", lambda name: None)
    with pytest.raises(download.DownloadError, match="FFmpeg"):
        download.download_video(VIDEO, tmp_path / "media", media=download.MediaOptions(audio_only=True, audio_format="mp3"))
    assert backend == []
    assert not (tmp_path / "media").exists()


def test_sidecars_are_opt_in_with_explicit_caption_languages(tmp_path, backend):
    media = download.MediaOptions(subtitles=("en", "de"), auto_subtitles=True,
                                  write_metadata=True, write_thumbnail=True)

    download.download_video(VIDEO, tmp_path, media=media)

    options = backend[0][1]
    assert options["writesubtitles"] is True
    assert options["writeautomaticsub"] is True
    assert options["subtitleslangs"] == ["en", "de"]
    assert options["writeinfojson"] is True
    assert options["writethumbnail"] is True


def test_format_preview_is_read_only_and_returns_only_display_fields(backend):
    formats = download.list_formats(VIDEO)

    assert formats[0]["format_id"] == "140"
    assert formats[0]["filesize_approx"] == 1048576
    assert "url" not in formats[0]
    assert not any(call[0] == "download" for call in backend)
    assert backend[1][2] is False
    assert backend[0][1]["cachedir"] is False
    assert backend[0][1]["skip_download"] is True
    assert "download_archive" not in backend[0][1]


def test_formats_cli_prints_audio_and_estimated_sizes(backend, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["youtube3", "download", "formats", VIDEO])
    main.main()
    output = capsys.readouterr().out
    assert "140" in output and "m4a" in output and "aac" in output
    assert "~1.0 MiB" in output
    assert "example.invalid" not in output


def test_playlist_audio_plan_uses_audio_archive_and_options(tmp_path, backend):
    media = download.MediaOptions(audio_only=True)
    plan = download.preview_playlist(PLAYLIST, tmp_path, media=media)
    assert plan.archive.name.endswith("-audio-native.txt")
    backend.clear()

    download.download_playlist(plan)

    assert backend[0][1]["format"] == "bestaudio"


def test_audio_dry_run_needs_no_extra_or_conversion_tools(tmp_path, monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "yt_dlp", None)
    monkeypatch.setattr(download.shutil, "which", lambda name: None)
    output = tmp_path / "media"
    media = download.MediaOptions(audio_only=True, audio_format="mp3", write_metadata=True)

    download.download_video(VIDEO, output, media=media, dry_run=True)

    printed = capsys.readouterr().out
    assert "mp3" in printed and "metadata" in printed
    assert not output.exists()


@pytest.mark.parametrize("flags", [["--audio-format", "mp3"], ["--audio-only", "--quality", "720"],
                                   ["--auto-subtitles"], ["--subtitles", "en,../de"], ["--subtitles", ""]])
def test_invalid_media_cli_combinations_fail_before_playlist_request(backend, monkeypatch, flags):
    monkeypatch.setattr(sys, "argv", ["youtube3", "download", "playlist", PLAYLIST, *flags])
    with pytest.raises(SystemExit) as error:
        main.main()
    assert error.value.code != 0
    assert backend == []


def test_explicit_archive_is_preserved_for_audio(tmp_path, backend):
    archive = tmp_path / "custom.txt"
    download.download_video(VIDEO, tmp_path, media=download.MediaOptions(audio_only=True), archive=archive)
    assert backend[0][1]["download_archive"] == str(archive)
