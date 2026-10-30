import json
import sys

import pytest
from PIL import Image, ImageChops

from youtube3 import artwork, playlist_artwork as pa
from youtube3.cli import artwork_playlist


@pytest.fixture
def inputs(tmp_path):
    background = tmp_path / "base.png"
    Image.new("RGB", (1280, 720), "navy").save(background)
    snapshot = {"playlist_id": "PLtest", "title": "A series", "items": [
        {"video_id": "v1", "position": 1, "title": "First"},
        {"video_id": "v1", "position": 2, "title": "Duplicate"},
        {"video_id": None, "position": 3, "available": False},
        {"video_id": "v4", "position": 4, "title": "Fourth"}]}
    return snapshot, background, tmp_path / "output"


def test_stable_mapping_duplicates_unavailable_range_and_numbering(inputs):
    snapshot, background, output = inputs
    manifest = pa.plan_playlist_artwork(snapshot, background, output, start=2, end=4, number_offset=98)
    assert not output.exists()
    assert [entry["video_id"] for entry in manifest["entries"]] == ["v1", None, "v4"]
    assert [entry["episode"] for entry in manifest["entries"]] == [100, 101, 102]
    assert manifest["entries"][1]["state"] == "unavailable"
    assert manifest["entries"][1]["render"] is None
    assert manifest["entries"][2]["render"]["output"].endswith("0004-v4.png")
    snapshot["items"].reverse()
    assert pa.plan_playlist_artwork(snapshot, background, output, start=2, end=4, number_offset=98) == manifest


def test_saved_plan_offline_render_images_cover_and_output_preservation(inputs, tmp_path):
    snapshot, background, output = inputs
    manifest = pa.plan_playlist_artwork(snapshot, background, output)
    path = tmp_path / "manifest.json"
    pa.save_manifest(manifest, path)
    loaded = pa.load_manifest(path)
    assert loaded == manifest
    pa.render_playlist_artwork(loaded)
    for entry in manifest["entries"] + [manifest["cover"]]:
        if not entry["render"]:
            continue
        with Image.open(entry["render"]["output"]) as image:
            expected = (1280, 1280) if entry is manifest["cover"] else (1280, 720)
            assert image.size == expected
            assert ImageChops.difference(image, Image.new("RGB", expected, "navy")).getbbox()
    before = (output / "0001-v1.png").read_bytes()
    with pytest.raises(artwork.ArtworkError, match="exists"):
        pa.render_playlist_artwork(loaded)
    assert (output / "0001-v1.png").read_bytes() == before


@pytest.mark.parametrize("mutation", ["duplicate_position", "unsafe_id", "invalid_range", "empty_range"])
def test_invalid_plan_rejected_before_file_generation(inputs, mutation):
    snapshot, background, output = inputs
    options = {}
    if mutation == "duplicate_position":
        snapshot["items"][1]["position"] = 1
    elif mutation == "unsafe_id":
        snapshot["items"][0]["video_id"] = "../escape"
    elif mutation == "invalid_range":
        options = {"start": 3, "end": 2}
    else:
        options = {"start": 99}
    with pytest.raises(artwork.ArtworkError):
        pa.plan_playlist_artwork(snapshot, background, output, **options)
    assert not output.exists()


def test_manifest_cannot_overwrite_background_or_image_output(inputs):
    snapshot, background, output = inputs
    manifest = pa.plan_playlist_artwork(snapshot, background, output)
    for destination in (background, output / "0001-v1.png"):
        with pytest.raises(artwork.ArtworkError, match="Manifest path"):
            pa.save_manifest(manifest, destination, overwrite=True)


def test_snapshot_cli_preview_no_account_calls_or_files(inputs, tmp_path, monkeypatch, capsys):
    snapshot, background, output = inputs
    source = tmp_path / "snapshot.json"
    source.write_text(json.dumps(snapshot), encoding="utf-8")
    monkeypatch.setattr(artwork_playlist, "client", lambda args: pytest.fail("offline called API"))
    monkeypatch.setattr(sys, "argv", ["playlist", "--snapshot", str(source), "--background", str(background),
                                      "--output-dir", str(output)])
    artwork_playlist.main()
    assert "Offline snapshot" in capsys.readouterr().out
    assert not output.exists()


def test_online_snapshot_reads_only_existing_client_methods():
    class Client:
        def playlist_snippet(self, playlist_id):
            assert playlist_id == "PLtest"
            return {"title": "A series"}

        def iterate_videos_in_playlist(self, playlist_id):
            yield {"items": [{"snippet": {"position": 0, "title": "First"}, "contentDetails": {"videoId": "v1"}},
                             {"snippet": {"position": 1, "title": "Private"}, "contentDetails": {"videoId": "v2"}}]}

        def video_details(self, ids):
            assert ids == ["v1", "v2"]
            return {"v1": {}}

    snapshot = pa.playlist_snapshot(Client(), "PLtest")
    assert [entry["available"] for entry in snapshot["items"]] == [True, False]
    assert [entry["position"] for entry in snapshot["items"]] == [1, 2]
