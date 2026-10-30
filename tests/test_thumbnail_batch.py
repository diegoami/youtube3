import json
import sys

import pytest
from PIL import Image

from youtube3 import playlist_artwork as pa, thumbnail_batch as tb
from youtube3.cli import artwork_apply


@pytest.fixture
def manifest(tmp_path):
    background = tmp_path / "base.png"
    Image.new("RGB", (1280, 720), "navy").save(background)
    snapshot = {"playlist_id": "PLtest", "title": "Series", "items": [
        {"video_id": "v1", "position": 1}, {"video_id": "v2", "position": 2}]}
    manifest = pa.plan_playlist_artwork(snapshot, background, tmp_path / "images")
    pa.render_playlist_artwork(manifest)
    return manifest


def prepared(fake, *uploads, owner="UCmine", eligible=True):
    f = fake({"items": [{"status": {"longUploadsStatus": "allowed" if eligible else "disallowed"}}]},
             {"items": [{"id": video_id, "snippet": {"channelId": owner}} for video_id in ("v1", "v2")]},
             *uploads)
    f.client._channel = {"id": "UCmine", "title": "Mine"}
    return f


def test_preview_has_fixed_ids_files_and_no_writes(fake, manifest):
    f = prepared(fake)
    plan = tb.plan_thumbnail_batch(f.client, manifest)
    assert [entry["video_id"] for entry in plan["entries"]] == ["v1", "v2"]
    assert all(request.method == "GET" for request in f.requests)
    assert plan["cost"] == 100
    assert all(entry["image"]["sha256"] for entry in plan["entries"])
    assert all("playlist-cover" not in entry["image"]["path"] for entry in plan["entries"])


def test_apply_only_thumbnails_correct_ids_media_and_checkpoint(fake, manifest, tmp_path):
    f = prepared(fake, {"items": []}, {"items": []})
    path = tmp_path / "results.json"
    report = tb.apply_thumbnail_batch(f.client, manifest, report_path=path)
    assert [entry["state"] for entry in report["entries"]] == ["successful", "successful"]
    writes = [request for request in f.requests if request.method != "GET"]
    assert [request.path for request in writes] == ["thumbnails/set", "thumbnails/set"]
    assert [request.params["videoId"] for request in writes] == ["v1", "v2"]
    assert all(request.headers["content-type"] == "image/png" for request in writes)
    assert all(request.raw.startswith(b"\x89PNG") for request in writes)
    assert json.loads(path.read_text(encoding="utf-8")) == report


def test_partial_failure_and_retry_only_failed_or_pending(fake, manifest, tmp_path):
    error = (403, {"error": {"code": 403, "message": "Refused", "errors": [{"reason": "forbidden"}]}})
    f = prepared(fake, {"items": []}, error)
    path = tmp_path / "results.json"
    with pytest.raises(tb.ThumbnailBatchError) as result:
        tb.apply_thumbnail_batch(f.client, manifest, report_path=path)
    report = result.value.report
    assert [entry["state"] for entry in report["entries"]] == ["successful", "failed"]
    assert report["entries"][1]["error"] == "HTTP 403"
    second = prepared(fake, {"items": []})
    complete = tb.apply_thumbnail_batch(second.client, manifest, previous=report, report_path=path)
    writes = [r for r in second.requests if r.method != "GET"]
    assert [r.params["videoId"] for r in writes] == ["v2"]
    assert all(entry["state"] == "successful" for entry in complete["entries"])


def test_stop_retains_unattempted_entries(fake, manifest):
    f = prepared(fake, (403, {"error": {"code": 403, "message": "Refused"}}))
    with pytest.raises(tb.ThumbnailBatchError) as result:
        tb.apply_thumbnail_batch(f.client, manifest)
    assert [e["state"] for e in result.value.report["entries"]] == ["failed", "pending"]


@pytest.mark.parametrize("problem", ["duplicate", "missing", "malformed", "large", "wrong_owner", "ineligible"])
def test_batch_preflight_rejects_before_any_write(fake, manifest, problem):
    f = prepared(fake, owner="UCother" if problem == "wrong_owner" else "UCmine", eligible=problem != "ineligible")
    if problem == "duplicate":
        manifest["entries"][1]["video_id"] = "v1"
    elif problem == "missing":
        from pathlib import Path
        Path(manifest["entries"][1]["render"]["output"]).unlink()
    elif problem == "malformed":
        from pathlib import Path
        Path(manifest["entries"][1]["render"]["output"]).write_bytes(b"invalid")
    elif problem == "large":
        with open(manifest["entries"][1]["render"]["output"], "ab") as output:
            output.truncate(2 * 1024 * 1024 + 1)
    with pytest.raises((tb.ThumbnailBatchError, ValueError)):
        tb.apply_thumbnail_batch(f.client, manifest)
    assert all(request.method == "GET" for request in f.requests)


def test_retry_mapping_or_image_changes_rejected(fake, manifest):
    f = prepared(fake)
    report = tb.plan_thumbnail_batch(f.client, manifest)
    report["entries"][0]["video_id"] = "unrelated"
    second = prepared(fake)
    with pytest.raises(tb.ThumbnailBatchError, match="mapping changed"):
        tb.apply_thumbnail_batch(second.client, manifest, previous=report)
    assert all(r.method == "GET" for r in second.requests)


def test_cli_preview_never_applies_or_saves(fake, manifest, tmp_path, monkeypatch, capsys):
    f = prepared(fake)
    path = tmp_path / "manifest.json"
    pa.save_manifest(manifest, path)
    report_path = tmp_path / "results.json"
    monkeypatch.setattr(artwork_apply, "client", lambda args: f.client)
    monkeypatch.setattr(sys, "argv", ["apply", str(path), "--report", str(report_path)])
    artwork_apply.main()
    assert "Dry run" in capsys.readouterr().out
    assert not report_path.exists()
    assert all(request.method == "GET" for request in f.requests)


def test_checkpoint_failure_preserves_applied_result(fake, manifest, tmp_path, monkeypatch):
    f = prepared(fake, {"items": []})
    original = tb.artwork.save_bytes
    calls = 0

    def fail_after_upload(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls > 1:
            raise OSError("disk full")
        return original(*args, **kwargs)

    monkeypatch.setattr(tb.artwork, "save_bytes", fail_after_upload)
    with pytest.raises(tb.ThumbnailBatchError) as result:
        tb.apply_thumbnail_batch(f.client, manifest, report_path=tmp_path / "result.json")
    assert [e["state"] for e in result.value.report["entries"]] == ["successful", "pending"]
    assert len([r for r in f.requests if r.method != "GET"]) == 1
