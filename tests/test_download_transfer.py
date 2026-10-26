"""Transfer limits validate offline and leave backend defaults untouched."""

import sys

import pytest

from youtube3 import download
from youtube3.cli import main
from youtube3.cli.download_options import rate_limit


@pytest.mark.parametrize(("text", "expected"), [
    ("1024", 1024), ("500K", 500 * 1024), ("1.5M", 1572864),
    ("2MiB", 2097152), ("2kb", 2048), ("1G", 1073741824),
])
def test_rate_units_are_binary_bytes_per_second(text, expected):
    assert rate_limit(text) == expected


@pytest.mark.parametrize("flags", [
    ["--limit-rate", "0"], ["--limit-rate", "-1"], ["--limit-rate", "inf"],
    ["--limit-rate", "2MB/s"], ["--limit-rate", "0.5B"],
    ["--retries", "-1"], ["--retries", "1.5"], ["--retries", "infinite"],
    ["--fragment-retries", "-1"],
])
@pytest.mark.parametrize("command", ["video", "playlist"])
def test_invalid_cli_limits_fail_before_any_backend_or_writes(tmp_path, monkeypatch, command, flags):
    def unexpected():
        raise AssertionError("Invalid settings must not import the backend")

    monkeypatch.setattr(download, "_backend", unexpected)
    monkeypatch.setattr(sys, "argv", ["youtube3", "download", command, "BaW_jenozKc",
                                     "--output", str(tmp_path / "media"), *flags])
    with pytest.raises(SystemExit) as error:
        main.main()
    assert error.value.code == 2
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("kwargs", [
    {"limit_rate": 0}, {"limit_rate": True}, {"limit_rate": 1.5},
    {"retries": -1}, {"retries": False}, {"fragment_retries": "2"},
])
def test_library_rejects_invalid_transfer_settings(kwargs):
    with pytest.raises(ValueError):
        download.TransferOptions(**kwargs)


def test_defaults_do_not_override_backend_transfer_policy(tmp_path):
    options = download._options(tmp_path, None, tmp_path / "done.txt", download.MediaOptions())
    assert not {"ratelimit", "retries", "fragment_retries"}.intersection(options)


def test_video_dry_run_displays_limits_without_backend_or_writes(tmp_path, monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "yt_dlp", None)
    monkeypatch.setattr(sys, "argv", ["youtube3", "download", "video", "BaW_jenozKc", "--dry-run",
                                     "--output", str(tmp_path / "media"), "--limit-rate", "1.5M",
                                     "--retries", "0", "--fragment-retries", "2"])
    main.main()
    output = capsys.readouterr().out
    assert "rate limit 1572864 bytes/s" in output
    assert "HTTP retries 0" in output
    assert "fragment retries 2" in output
    assert not list(tmp_path.iterdir())
