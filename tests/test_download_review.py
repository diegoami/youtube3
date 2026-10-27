"""Reproductions for milestone findings #122–#124 using synthetic inputs only."""

from dataclasses import replace
import json
from types import SimpleNamespace
import sys

import pytest

from youtube3 import download
from youtube3 import download_batch as batch


VIDEO = "BaW_jenozKc"
PLAYLIST = "https://www.youtube.com/playlist?list=PL0123456789"
UPSTREAM_BLOCKS = [
    "This content isn't available, try again later. The current session has been rate-limited by YouTube "
    "for up to an hour. It is recommended to use `-t sleep` to add a delay between video requests "
    "to avoid exceeding the rate limit.",
    "This content isn't available, try again later. Your account has been rate-limited by YouTube "
    "for up to an hour. It is recommended to use `-t sleep` to add a delay between video requests "
    "to avoid exceeding the rate limit.",
    "Video unavailable. YouTube is requiring a captcha challenge before playback",
]


@pytest.mark.parametrize("message", UPSTREAM_BLOCKS)
@pytest.mark.parametrize("cookies", [False, True])
def test_upstream_extractor_blocks_stop_batch_and_preserve_checkpoint(tmp_path, monkeypatch, capsys, message, cookies):
    calls = []

    class Downloader:
        def __init__(self, options):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def extract_info(self, *args, **kwargs):
            calls.append(1)
            raise RuntimeError(message)

    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(
        YoutubeDL=Downloader, utils=SimpleNamespace(DownloadError=RuntimeError)))
    access = download.AccessOptions(browser="firefox") if cookies else download.AccessOptions()
    plan = download.PlaylistPlan(
        PLAYLIST, "Synthetic", tmp_path / "media", tmp_path / "archive",
        (download.PlaylistEntry(1, VIDEO, "Synthetic"), download.PlaylistEntry(2, "abcdefghijk", "Synthetic")),
        access=access)
    report = tmp_path / "report.json"
    result = batch.download_batch(plan, continue_on_error=True, report=report)
    assert len(calls) == 1
    assert [entry.status for entry in result.entries] == ["failed", "not_attempted"]
    assert result.entries[0].reason == "blocked"
    assert json.loads(report.read_text())["entries"][1]["status"] == "not_attempted"
    output = capsys.readouterr().out
    assert "captcha" in output.lower() if "captcha" in message else "rate limit" in output.lower()
    assert "HTTP 429" not in output  # A session limit is not a transport status.
    assert "-t sleep" not in output  # This is not a youtube3 CLI option.


@pytest.mark.parametrize("operation, destination", [
    ("video", "output"), ("video", "archive"),
    ("preview", "output"), ("preview", "archive"),
    ("playlist", "output"), ("playlist", "archive"),
    ("batch", "output"), ("batch", "archive"), ("batch", "report"),
])
def test_cookie_collisions_reject_before_backend_and_preserve_source(tmp_path, monkeypatch, operation, destination):
    source = tmp_path / "synthetic-session.txt"
    original = "# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t0\tsynthetic\tfixture-value\n"
    source.write_text(original)
    paths = {"output": tmp_path / "media", "archive": tmp_path / "archive", "report": tmp_path / "result.json"}
    paths[destination] = source
    access = download.AccessOptions(cookies=source)
    plan = download.PlaylistPlan(PLAYLIST, "Synthetic", paths["output"], paths["archive"],
                                (download.PlaylistEntry(1, VIDEO, "Synthetic"),))
    # Apply/retry paths must validate a manually reconstructed plan as well as a
    # plan produced by metadata enumeration. No credentials are restored from it.
    report = tmp_path / "retry-input.json"
    report.write_text(json.dumps(batch._payload(plan, None, [batch.BatchEntry(1, VIDEO, "Synthetic", "failed")])))
    retry, _ = batch.retry_plan(report)
    retry = replace(retry, access=access)

    def forbidden():
        raise AssertionError("A cookie collision must be rejected before backend access")

    monkeypatch.setattr(download, "_backend", forbidden)
    actions = {
        "video": lambda: download.download_video(VIDEO, paths["output"], archive=paths["archive"], access=access),
        "preview": lambda: download.preview_playlist(PLAYLIST, paths["output"], archive=paths["archive"], access=access),
        "playlist": lambda: download.download_playlist(retry),
        "batch": lambda: batch.download_batch(retry, report=paths["report"]),
    }
    with pytest.raises(ValueError, match="Cookie source"):
        actions[operation]()
    assert source.read_text() == original


@pytest.mark.parametrize("expiry", ["1792358461.5", "1792358461.123456"])
def test_fractional_expiry_loads_in_real_backend_without_warning_or_source_change(tmp_path, capsys, expiry):
    yt_dlp = pytest.importorskip("yt_dlp")
    source = tmp_path / "synthetic-session.txt"
    content = f"# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t{expiry}\tsynthetic\tfixture-value\n"
    source.write_text(content)
    with yt_dlp.YoutubeDL({"quiet": True, "cachedir": False, **download.AccessOptions(cookies=source).backend_options()}) as backend:
        assert len(list(backend.cookiejar)) == 1
    assert not capsys.readouterr().err
    assert source.read_text() == content


def test_invalid_expiry_names_line_without_cookie_contents(tmp_path):
    source = tmp_path / "synthetic-session.txt"
    source.write_text("# Netscape HTTP Cookie File\n# synthetic comment\n"
                      ".youtube.com\tTRUE\t/\tTRUE\tinvalid-expiry\tsynthetic\tfixture-value\n")
    with pytest.raises(download.DownloadError) as error:
        download.AccessOptions(cookies=source).backend_options()
    assert "line 3" in str(error.value)
    assert "invalid-expiry" not in str(error.value) and "fixture-value" not in str(error.value)
