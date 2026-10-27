"""Download setup and blocked-extraction diagnostics without network access."""

import sys
from types import SimpleNamespace

import pytest

from youtube3 import download
from youtube3 import download_batch as batch


VIDEO = "BaW_jenozKc"


@pytest.fixture
def backend(monkeypatch):
    calls = []

    class Downloader:
        def __init__(self, options):
            calls.append(options)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def download(self, urls):
            raise RuntimeError("HTTP Error 429: Too Many Requests")

        def extract_info(self, *args, **kwargs):
            raise RuntimeError("Sign in to confirm you’re not a bot. Use --cookies-from-browser")

    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(
        YoutubeDL=Downloader, utils=SimpleNamespace(DownloadError=RuntimeError)))
    return calls


@pytest.mark.parametrize("executables, expected", [
    ({"deno": "/bin/deno"}, {"deno": {"path": "/bin/deno"}}),
    ({"node": "/bin/node"}, {"node": {"path": "/bin/node"}}),
    ({"qjs": "/bin/qjs"}, {"quickjs": {"path": "/bin/qjs"}}),
    ({"deno": "/bin/deno", "node": "/bin/node"},
     {"deno": {"path": "/bin/deno"}, "node": {"path": "/bin/node"}}),
])
def test_available_runtimes_are_enabled_for_extraction(monkeypatch, backend, tmp_path, executables, expected):
    monkeypatch.setattr(download.shutil, "which", executables.get)
    with pytest.raises(download.DownloadError):
        download.download_video(VIDEO, tmp_path)
    assert backend[0]["js_runtimes"] == expected


@pytest.mark.parametrize("operation", ["video", "formats", "playlist", "preview"])
def test_shared_setup_and_blocked_errors(monkeypatch, backend, tmp_path, capsys, operation):
    monkeypatch.setattr(download.shutil, "which", lambda name: None)
    plan = download.PlaylistPlan(
        "https://www.youtube.com/playlist?list=PL0123456789", "Offline", tmp_path / "media",
        tmp_path / "archive", (download.PlaylistEntry(1, VIDEO, "Offline"),))
    actions = {
        "video": lambda: download.download_video(VIDEO, plan.output),
        "formats": lambda: download.list_formats(VIDEO),
        "playlist": lambda: download.download_playlist(plan),
        "preview": lambda: download.preview_playlist("PL0123456789", plan.output),
    }
    with pytest.raises(download.DownloadError) as error:
        actions[operation]()
    assert len(backend) == 1  # No wrapper retry of a blocked request.
    assert backend[0]["js_runtimes"] == {}
    message = str(error.value)
    assert "--cookies" not in message
    assert "rate limit" in message if operation == "video" else "bot challenge" in message
    assert "JavaScript runtime does not" in message
    warning = capsys.readouterr().err
    assert "No JavaScript runtime found on PATH" in warning
    assert "Deno" in warning and "https://github.com/yt-dlp/yt-dlp/wiki/EJS" in warning


def test_batch_retry_rechecks_current_runtime_without_changing_reports(monkeypatch, backend, tmp_path, capsys):
    monkeypatch.setattr(download.shutil, "which", lambda name: "/bin/node" if name == "node" else None)
    plan = download.PlaylistPlan(
        "https://www.youtube.com/playlist?list=PL0123456789", "Offline", tmp_path / "media",
        tmp_path / "archive", (download.PlaylistEntry(1, VIDEO, "Offline"),))
    report = tmp_path / "report.json"
    result = batch.download_batch(plan, report=report)
    assert result.failed == 1
    assert backend[0]["js_runtimes"] == {"node": {"path": "/bin/node"}}
    assert "bot challenge" in capsys.readouterr().out
    assert "--cookies" not in report.read_text()

    def forbidden(name):
        raise AssertionError("Report preview must not probe dependencies")

    monkeypatch.setattr(download.shutil, "which", forbidden)
    retry, quality = batch.retry_plan(report)
    monkeypatch.setattr(download.shutil, "which", lambda name: "/bin/deno" if name == "deno" else None)
    assert batch.download_batch(retry, quality=quality).failed == 1
    assert len(backend) == 2
    assert backend[1]["js_runtimes"] == {"deno": {"path": "/bin/deno"}}


def test_real_backend_accepts_detected_runtime_options(monkeypatch):
    yt_dlp = pytest.importorskip("yt_dlp")
    monkeypatch.setattr(download.shutil, "which", lambda name: "/test/node" if name == "node" else None)
    with yt_dlp.YoutubeDL({"quiet": True, "cachedir": False, **download._runtime_options(quiet=True)}) as downloader:
        assert downloader.params["js_runtimes"] == {"node": {"path": "/test/node"}}


def test_dry_run_does_not_probe_runtime(monkeypatch, tmp_path):
    def forbidden(name):
        raise AssertionError("An offline dry run must not probe dependencies")

    monkeypatch.setattr(download.shutil, "which", forbidden)
    monkeypatch.setitem(sys.modules, "yt_dlp", None)
    download.download_video(VIDEO, tmp_path / "media", dry_run=True)
    assert not (tmp_path / "media").exists()


def test_real_backend_logger_filters_auth_advice_and_respects_quiet(monkeypatch, capsys):
    yt_dlp = pytest.importorskip("yt_dlp")
    monkeypatch.setattr(download.shutil, "which", lambda name: None)
    options = {"quiet": True, "cachedir": False, **download._runtime_options(quiet=True)}
    with yt_dlp.YoutubeDL(options) as downloader:
        downloader.to_screen("Extractor progress")
        downloader.report_warning("HTTP Error 429: Too Many Requests")
        with pytest.raises(yt_dlp.utils.DownloadError):
            downloader.report_error("Sign in to confirm you're not a bot. Use --cookies-from-browser")
    captured = capsys.readouterr()
    assert "Extractor progress" not in captured.out
    assert "--cookies" not in captured.err
    assert "rate limit" in captured.err and "bot challenge" in captured.err


@pytest.mark.parametrize("message", ["Disk full", "Video unavailable", "FFmpeg failed"])
def test_unrelated_errors_keep_their_message(message):
    assert download._failure_message(RuntimeError(message)) == message
