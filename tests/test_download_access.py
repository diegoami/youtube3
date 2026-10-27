"""Synthetic cookie access, pacing and blocked batches; never use real profiles."""

import json
from dataclasses import replace
import sys
from types import SimpleNamespace

import pytest

from youtube3 import download
from youtube3 import download_batch as batch
from youtube3.cli import main


VIDEO = "BaW_jenozKc"


def test_cookie_dry_run_does_not_open_source_or_import_backend(tmp_path, monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "yt_dlp", None)
    monkeypatch.setattr(sys, "argv", ["youtube3", "download", "video", VIDEO, "--dry-run",
                                     "--cookies", str(tmp_path / "missing-session.txt"),
                                     "--sleep-interval", "7", "--output", str(tmp_path / "media")])
    main.main()
    assert "7" in capsys.readouterr().out
    assert not list(tmp_path.iterdir())


def test_block_stops_continuation_and_keeps_unattempted_entries(tmp_path, monkeypatch):
    plan = download.PlaylistPlan(
        "https://www.youtube.com/playlist?list=PL0123456789", "Synthetic", tmp_path / "media",
        tmp_path / "archive", tuple(download.PlaylistEntry(i, value, "Synthetic") for i, value in
                                     enumerate([VIDEO, "abcdefghijk"], 1)))
    monkeypatch.setattr(download, "_backend", lambda: None)
    calls = []

    def blocked(selection, **kwargs):
        calls.append(selection)
        raise download.DownloadBlockedError("YouTube rate limit (HTTP 429)")

    monkeypatch.setattr(download, "download_playlist", blocked)
    report = tmp_path / "report.json"
    result = batch.download_batch(plan, continue_on_error=True, report=report)
    assert len(calls) == 1
    assert [entry.status for entry in result.entries] == ["failed", "not_attempted"]
    assert json.loads(report.read_text())["entries"][1]["status"] == "not_attempted"


def test_cookie_sources_are_mutually_exclusive():
    with pytest.raises(ValueError):
        download.AccessOptions(cookies="synthetic.txt", browser="firefox")


def test_cookie_report_requires_explicit_resupply_and_omits_source(tmp_path, monkeypatch):
    access = download.AccessOptions(browser="firefox", browser_profile="synthetic-profile")
    plan = download.PlaylistPlan(
        "https://www.youtube.com/playlist?list=PL0123456789", "Synthetic", tmp_path / "media",
        tmp_path / "archive", (download.PlaylistEntry(1, VIDEO, "Synthetic"),), access=access)
    monkeypatch.setattr(download, "_backend", lambda: None)
    monkeypatch.setattr(download, "download_playlist", lambda *a, **k: (_ for _ in ()).throw(
        download.DownloadError("Synthetic failure")))
    path = tmp_path / "report.json"
    batch.download_batch(plan, report=path)
    text = path.read_text()
    assert "firefox" not in text and "synthetic-profile" not in text
    retry, quality = batch.retry_plan(path)
    assert retry.requires_cookies and not retry.access.enabled
    with pytest.raises(download.DownloadError, match="cookie"):
        batch.download_batch(retry, quality=quality)


def test_batch_paces_actual_attempts(tmp_path, monkeypatch):
    plan = download.PlaylistPlan(
        "https://www.youtube.com/playlist?list=PL0123456789", "Synthetic", tmp_path / "media",
        tmp_path / "archive", (download.PlaylistEntry(1, VIDEO, "Synthetic"),
                               download.PlaylistEntry(2, "abcdefghijk", "Synthetic")),
        transfer=download.TransferOptions(sleep_interval=7))
    monkeypatch.setattr(download, "_backend", lambda: None)
    events = []
    monkeypatch.setattr(download.time, "sleep", lambda seconds: events.append(("sleep", seconds)))
    monkeypatch.setattr(download, "download_playlist", lambda plan, **kw: events.append(plan.entries[0].video_id))
    batch.download_batch(plan)
    assert events == [VIDEO, ("sleep", 7), "abcdefghijk"]


def test_file_cookies_are_memory_only_and_backend_errors_do_not_echo_content(tmp_path, monkeypatch, capsys):
    source = tmp_path / "synthetic-session.txt"
    content = "# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t0\tsynthetic\tfixture-value\n"
    source.write_text(content)
    seen = []

    class Downloader:
        def __init__(self, options):
            seen.append(options)
            options["logger"].warning("Synthetic malformed cookie line: fixture-value")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def download(self, urls):
            raise RuntimeError("Synthetic cookie error: fixture-value")

    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(
        YoutubeDL=Downloader, utils=SimpleNamespace(DownloadError=RuntimeError)))
    with pytest.raises(download.DownloadError) as error:
        download.download_video(VIDEO, tmp_path / "media", access=download.AccessOptions(cookies=source))
    assert "fixture-value" not in str(error.value)
    assert "fixture-value" not in capsys.readouterr().err
    assert seen[0]["cookiefile"].getvalue() == content
    assert source.read_text() == content


def test_pacing_survives_report_retry(tmp_path, monkeypatch):
    plan = download.PlaylistPlan(
        "https://www.youtube.com/playlist?list=PL0123456789", "Synthetic", tmp_path / "media",
        tmp_path / "archive", (download.PlaylistEntry(1, VIDEO, "Synthetic"),))
    plan = replace(plan, transfer=download.TransferOptions(sleep_interval=9))
    monkeypatch.setattr(download, "_backend", lambda: None)
    monkeypatch.setattr(download, "download_playlist", lambda *a, **k: (_ for _ in ()).throw(
        download.DownloadError("Synthetic failure")))
    path = tmp_path / "report.json"
    batch.download_batch(plan, report=path)
    retry, _ = batch.retry_plan(path)
    assert retry.transfer.sleep_interval == 9


@pytest.mark.parametrize("body", [
    "fixture-value", ".youtube.com\tTRUE\t/\tTRUE\tfixture-value\tname\tvalue",
    "youtube.com\tTRUE\t/\tTRUE\t0\tname\tfixture-value",
])
def test_malformed_cookie_input_never_reaches_backend_or_echoes_lines(tmp_path, monkeypatch, capsys, body):
    source = tmp_path / "synthetic-session.txt"
    source.write_text("# Netscape HTTP Cookie File\n" + body + "\n")
    calls = []
    monkeypatch.setattr(download, "_backend", lambda: calls.append("import") or None)
    with pytest.raises(download.DownloadError) as error:
        download.download_video(VIDEO, tmp_path / "media", access=download.AccessOptions(cookies=source))
    assert "fixture-value" not in str(error.value)
    assert "fixture-value" not in capsys.readouterr().err
    assert not (tmp_path / "media").exists()


def test_real_cookiejar_load_and_close_preserve_source(tmp_path):
    yt_dlp = pytest.importorskip("yt_dlp")
    source = tmp_path / "synthetic-session.txt"
    content = "# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t0\tsynthetic\tfixture-value\n"
    source.write_text(content)
    options = {"quiet": True, "cachedir": False}
    download._session_options(options, download.AccessOptions(cookies=source))
    with yt_dlp.YoutubeDL(options) as downloader:
        assert len(list(downloader.cookiejar)) == 1
    assert source.read_text() == content


@pytest.mark.parametrize("command", ["video", "formats", "playlist", "retry"])
def test_invalid_cookie_cli_options_fail_without_browser_access(monkeypatch, command):
    monkeypatch.setattr(sys, "argv", ["youtube3", "download", command, VIDEO,
                                     "--cookies", "synthetic-session.txt", "--cookies-from-browser", "firefox"])
    with pytest.raises(SystemExit) as error:
        main.main()
    assert error.value.code == 2


def test_browser_profile_routing_does_not_open_browser(monkeypatch):
    access = download.AccessOptions(browser="firefox", browser_profile="synthetic-profile")
    assert access.backend_options() == {"cookiesfrombrowser": ("firefox", "synthetic-profile", None, None)}


def test_cookie_source_cannot_be_archive(tmp_path, monkeypatch):
    source = tmp_path / "synthetic-session.txt"
    monkeypatch.setitem(sys.modules, "yt_dlp", None)
    with pytest.raises(ValueError, match="Cookie source"):
        download.download_video(VIDEO, tmp_path / "media", archive=source,
                                access=download.AccessOptions(cookies=source))


@pytest.mark.parametrize("message", ["HTTP Error 429", "HTTP 429", "Too Many Requests",
                                    "Sign in to confirm you're not a bot"])
def test_block_classification_is_structured(message):
    assert isinstance(download._extraction_error(RuntimeError(message), download.AccessOptions()),
                      download.DownloadBlockedError)


def test_ordinary_numeric_error_is_not_a_block():
    error = download._extraction_error(RuntimeError("Video 429 unavailable"), download.AccessOptions())
    assert not isinstance(error, download.DownloadBlockedError)
