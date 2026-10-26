"""Report validation and offline retry behavior."""

from dataclasses import asdict
import json
import sys

import pytest

from youtube3 import download
from youtube3 import download_batch as batch
from youtube3.cli import main


@pytest.fixture
def report(tmp_path):
    path = tmp_path / "report.json"
    payload = {
        "schema_version": 1, "playlist_url": "https://www.youtube.com/playlist?list=PL0123456789",
        "playlist_title": "Original playlist", "output": str(tmp_path / "media"),
        "archive": str(tmp_path / "done.txt"), "quality": 720,
        "media": asdict(download.MediaOptions()),
        "entries": [{"position": 8, "video_id": "BaW_jenozKc", "title": "Video",
                     "status": "failed", "reason": "download_failed"}],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path, payload


@pytest.mark.parametrize(("field", "value"), [
    ("schema_version", 2), ("schema_version", True), ("quality", 0), ("quality", True),
    ("output", "relative"), ("archive", None), ("playlist_url", "https://example.com/"),
    ("media", {}), ("entries", None), ("playlist_title", None),
])
def test_invalid_report_is_rejected_offline(report, field, value, monkeypatch):
    path, payload = report
    payload[field] = value
    path.write_text(json.dumps(payload))
    monkeypatch.setitem(sys.modules, "yt_dlp", None)
    with pytest.raises(download.DownloadError, match="Invalid download report"):
        batch.retry_plan(path)


@pytest.mark.parametrize(("field", "value"), [
    ("video_id", "https://example.com"), ("video_id", "https://youtu.be/BaW_jenozKc"),
    ("position", 0), ("position", True), ("title", None), ("status", "unknown"),
])
def test_invalid_entry_is_rejected(report, field, value):
    path, payload = report
    payload["entries"][0][field] = value
    path.write_text(json.dumps(payload))
    with pytest.raises(download.DownloadError, match="Invalid download report"):
        batch.retry_plan(path)


@pytest.mark.parametrize("content", ["not json", "[]", "null"])
def test_malformed_report_is_actionable(tmp_path, content):
    path = tmp_path / "bad.json"
    path.write_text(content)
    with pytest.raises(download.DownloadError, match="download report"):
        batch.retry_plan(path)


def test_retry_skips_completed_id_without_optional_backend(report, monkeypatch):
    path, payload = report
    plan, quality = batch.retry_plan(path)
    plan.archive.write_text("youtube BaW_jenozKc\n")
    monkeypatch.setitem(sys.modules, "yt_dlp", None)

    result = batch.download_batch(plan, quality=quality)

    assert result.entries[0].status == "skipped"
    assert result.entries[0].reason == "archived"
    assert not plan.output.exists()


@pytest.mark.parametrize("command", ["playlist", "retry"])
def test_preview_rejects_report_output_without_writing(tmp_path, monkeypatch, command):
    path = tmp_path / "results.json"
    monkeypatch.setattr(sys, "argv", ["youtube3", "download", command, "PL0123456789",
                                     "--report", str(path)])
    with pytest.raises(SystemExit) as error:
        main.main()
    assert error.value.code == 2
    assert not path.exists()


def test_retry_cli_uses_original_selection_and_can_write_new_report(report, monkeypatch, capsys):
    path, payload = report
    plan, _ = batch.retry_plan(path)
    plan.archive.write_text("youtube BaW_jenozKc\n")
    result_path = path.parent / "retry.json"
    monkeypatch.setitem(sys.modules, "yt_dlp", None)
    monkeypatch.setattr(sys, "argv", ["youtube3", "download", "retry", str(path), "--apply",
                                     "--report", str(result_path)])
    main.main()
    assert "1 skipped" in capsys.readouterr().out
    assert json.loads(result_path.read_text())["entries"][0]["status"] == "skipped"
