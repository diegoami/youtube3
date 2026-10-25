"""Playlist selection and archives over canned responses, without network access."""

import sys
from types import SimpleNamespace

import pytest

from youtube3 import download
from youtube3.cli import main


PLAYLIST = "PL0123456789abcdef"
VIDEO = "BaW_jenozKc"
SECOND = "abcdefghijk"


@pytest.fixture
def backend(monkeypatch):
    calls = []
    entries = [
        {"id": VIDEO, "title": "First", "playlist_index": 2},
        {"id": SECOND, "title": "Second", "playlist_index": 3},
    ]

    class FakeDownloader:
        def __init__(self, options):
            self.options = options
            calls.append(("options", options))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def extract_info(self, url, *, download, **kwargs):
            calls.append(("extract", url, download, kwargs))
            if not download:
                return {"_type": "playlist", "title": "Example playlist", "entries": entries}
            return {"id": url.split("v=")[-1]}

        def download(self, urls):
            calls.append(("download", urls))
            return 0

    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(
        YoutubeDL=FakeDownloader, utils=SimpleNamespace(DownloadError=RuntimeError),
    ))
    return calls, entries


@pytest.mark.parametrize("value", [PLAYLIST, f"https://www.youtube.com/playlist?list={PLAYLIST}",
                                   f"https://www.youtube.com/watch?v={VIDEO}&list={PLAYLIST}"])
def test_playlist_input_selects_only_the_explicit_playlist(value):
    assert download.playlist_url(value) == f"https://www.youtube.com/playlist?list={PLAYLIST}"


@pytest.mark.parametrize("value", [VIDEO[:4], "https://example.com/playlist?list=" + PLAYLIST,
                                   "https://youtube.com/watch?v=" + VIDEO])
def test_invalid_playlist_is_rejected(value):
    with pytest.raises(ValueError):
        download.playlist_url(value)


def test_preview_reads_playlist_and_archive_but_never_downloads_or_writes(tmp_path, backend):
    calls, entries = backend
    archive = tmp_path / "completed.txt"
    archive.write_text(f"youtube {VIDEO}\n", encoding="utf-8")
    before = archive.read_bytes()
    output = tmp_path / "media"

    plan = download.preview_playlist(PLAYLIST, output, start=2, end=3, archive=archive)

    assert [entry.position for entry in plan.entries] == [2, 3]
    assert [entry.video_id for entry in plan.entries] == [VIDEO, SECOND]
    assert plan.entries[0].skip_reason == "archived"
    assert plan.entries[1].skip_reason is None
    assert not output.exists()
    assert archive.read_bytes() == before
    options = calls[0][1]
    assert options["playlist_items"] == "2:3"
    assert options["extract_flat"] is True
    assert "download_archive" not in options
    assert all(call[0] != "download" for call in calls)
    assert calls[1][2] is False


def test_default_cli_previews_and_lists_entries_without_apply(tmp_path, backend, monkeypatch, capsys):
    calls, _ = backend
    output = tmp_path / "media"
    monkeypatch.setattr(sys, "argv", ["youtube3", "download", "playlist", PLAYLIST, "--output", str(output)])

    main.main()

    printed = capsys.readouterr().out
    assert "First" in printed and "Second" in printed
    assert "--apply" in printed
    assert not output.exists()
    assert not any(call[0] == "extract" and call[2] for call in calls)


def test_apply_downloads_exact_preview_ids_in_order_with_original_positions(tmp_path, backend):
    calls, _ = backend
    plan = download.preview_playlist(PLAYLIST, tmp_path / "media", start=2, end=3)
    calls.clear()

    download.download_playlist(plan, quality=720)

    options = calls[0][1]
    assert "%(playlist_index)05d" in options["outtmpl"]
    assert options["download_archive"] == str(plan.archive)
    assert "[height<=720]" in options["format"]
    assert options["noplaylist"] is True
    requests = [call for call in calls if call[0] == "extract"]
    assert [call[1] for call in requests] == [download.video_url(VIDEO), download.video_url(SECOND)]
    assert [call[3]["extra_info"]["playlist_index"] for call in requests] == [2, 3]
    assert all(call[2] for call in requests)


def test_archived_unavailable_and_duplicate_entries_are_not_downloaded(tmp_path, backend):
    calls, entries = backend
    archive = tmp_path / "done.txt"
    archive.write_text(f"youtube {VIDEO}\n", encoding="utf-8")
    entries.extend([
        {"id": "lmnopqrstuv", "title": "Private video", "availability": "private", "playlist_index": 4},
        {"id": SECOND, "title": "Duplicate", "playlist_index": 5},
        {"title": "Removed video", "playlist_index": 6},
    ])
    plan = download.preview_playlist(PLAYLIST, tmp_path / "media", archive=archive)
    assert [entry.skip_reason for entry in plan.entries] == ["archived", None, "unavailable", "duplicate", "unavailable"]
    calls.clear()

    download.download_playlist(plan)

    assert [call[1] for call in calls if call[0] == "extract"] == [download.video_url(SECOND)]


def test_empty_playlist_is_a_noop_without_creating_output(tmp_path, backend):
    calls, entries = backend
    entries.clear()
    output = tmp_path / "media"
    plan = download.preview_playlist(PLAYLIST, output)
    calls.clear()

    download.download_playlist(plan)

    assert not calls
    assert not output.exists()


@pytest.mark.parametrize(("start", "end"), [(0, None), (-1, 3), (3, 2), (1, 0)])
def test_invalid_range_fails_before_loading_extra(tmp_path, monkeypatch, start, end):
    monkeypatch.setitem(sys.modules, "yt_dlp", None)
    with pytest.raises(ValueError, match="range"):
        download.preview_playlist(PLAYLIST, tmp_path, start=start, end=end)


def test_missing_extra_is_actionable_for_playlist_preview(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "yt_dlp", None)
    with pytest.raises(download.DownloadError, match=r'youtube3\[download\]'):
        download.preview_playlist(PLAYLIST, tmp_path)


def test_single_video_archive_skips_the_id_without_fetching_or_loading_extra(tmp_path, monkeypatch, capsys):
    archive = tmp_path / ".youtube3-download-archive.txt"
    archive.write_text(f"youtube {VIDEO}\n", encoding="utf-8")
    monkeypatch.setitem(sys.modules, "yt_dlp", None)

    download.download_video(VIDEO, tmp_path)

    assert "archived" in capsys.readouterr().out


def test_playlist_failure_is_an_error_and_does_not_mark_completion(tmp_path, backend, monkeypatch):
    plan = download.preview_playlist(PLAYLIST, tmp_path / "media")

    def fail(self, *args, **kwargs):
        raise RuntimeError("Download interrupted")

    monkeypatch.setattr(sys.modules["yt_dlp"].YoutubeDL, "extract_info", fail)
    with pytest.raises(download.DownloadError, match="interrupted"):
        download.download_playlist(plan)
    assert not plan.archive.exists()


def test_apply_cli_prints_preview_before_download(tmp_path, backend, monkeypatch, capsys):
    applied = []

    def apply(plan, **kwargs):
        assert "First" in capsys.readouterr().out
        applied.append((plan, kwargs))

    monkeypatch.setattr(download, "download_playlist", apply)
    monkeypatch.setattr(sys, "argv", ["youtube3", "download", "playlist", PLAYLIST,
                                     "--output", str(tmp_path), "--quality", "720", "--apply"])

    main.main()

    assert len(applied) == 1
    assert applied[0][1] == {"quality": 720}
    assert "complete" in capsys.readouterr().out


@pytest.mark.parametrize("flags", [["--quality", "0"], ["--apply", "--dry-run"]])
def test_invalid_cli_options_do_not_fetch_metadata(backend, monkeypatch, flags):
    calls, _ = backend
    monkeypatch.setattr(sys, "argv", ["youtube3", "download", "playlist", PLAYLIST, *flags])
    with pytest.raises(SystemExit) as error:
        main.main()
    assert error.value.code != 0
    assert not calls


def test_custom_archive_parent_is_created_only_when_applying(tmp_path, backend):
    archive = tmp_path / "state" / "completed.txt"
    plan = download.preview_playlist(PLAYLIST, tmp_path / "media", archive=archive)
    assert not archive.parent.exists()

    download.download_playlist(plan)

    assert archive.parent.is_dir()


def test_unreadable_archive_is_an_actionable_error(tmp_path, backend):
    archive = tmp_path / "not-an-archive"
    archive.mkdir()
    with pytest.raises(download.DownloadError, match="Cannot read download archive"):
        download.preview_playlist(PLAYLIST, tmp_path / "media", archive=archive)


def test_playlist_extraction_failure_is_an_actionable_error(tmp_path, backend, monkeypatch):
    def fail(self, *args, **kwargs):
        raise RuntimeError("Playlist unavailable")

    monkeypatch.setattr(sys.modules["yt_dlp"].YoutubeDL, "extract_info", fail)
    with pytest.raises(download.DownloadError, match="Playlist unavailable"):
        download.preview_playlist(PLAYLIST, tmp_path / "media")
