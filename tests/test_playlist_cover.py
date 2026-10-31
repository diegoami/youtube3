import sys

import pytest
from PIL import Image

from youtube3 import playlist_cover as pc
from youtube3.cli import playlist_cover as cli


@pytest.fixture
def image(tmp_path):
    path = tmp_path / "cover.png"
    Image.new("RGB", (1280, 1280), "navy").save(path)
    return path


def existing():
    return {"id": "hero-id", "snippet": {"playlistId": "PLtest", "type": "hero", "width": 1280, "height": 1280}}


def prepare(fake, *responses):
    f = fake(*responses)
    f.client._channel = {"id": "UCmine", "title": "Mine"}
    return f


def reads(hero=True):
    return ({"items": [{"snippet": {"channelId": "UCmine"}}]}, {"items": [existing()] if hero else []})


@pytest.mark.parametrize("hero", [False, True])
def test_cover_preview_and_media_insert_or_update(fake, image, hero):
    f = prepare(fake, *reads(hero), *reads(hero), {"id": "new-image"})
    result = f.client.set_playlist_cover("PLtest", image, apply=True)
    assert result["applied"]
    assert result["plan"]["action"] == ("update" if hero else "insert")
    assert result["response"]["id"] == "new-image"
    writes = [r for r in f.requests if r.method != "GET"]
    assert len(writes) == 1
    request = writes[0]
    assert request.path == "playlistImages"
    assert request.method == ("PUT" if hero else "POST")
    body = request.raw if isinstance(request.raw, bytes) else request.raw.encode()
    if hero:
        assert request.params.get("id") == "hero-id"
        assert "part" not in request.params
        assert b'"snippet"' not in body
    else:
        assert request.params["part"] == "snippet"
        assert "id" not in request.params
        assert b'"playlistId": "PLtest"' in body
        assert b'"type": "hero"' in body
    # YouTube derives dimensions from the media. Sending the otherwise optional
    # fields reproduced HTTP 400 in owner-approved G5; required fields succeeded.
    assert b'"width"' not in body
    assert b'"height"' not in body
    assert b'"id": "hero-id"' in body if hero else b'"id": "hero-id"' not in body
    assert b"\x89PNG" in body
    assert all(r.params.get("parent") == "PLtest" for r in f.requests if r.path == "playlistImages" and r.method == "GET")


def test_preview_no_write(fake, image):
    f = prepare(fake, *reads())
    result = f.client.set_playlist_cover("PLtest", image)
    assert result["applied"] is False and result["response"] is None
    assert all(r.method == "GET" for r in f.requests)


def test_update_encodes_exact_existing_id_without_adding_query_parameters(fake, image):
    hero = existing()
    hero["id"] = "hero&part=snippet?other=1"
    responses = ({"items": [{"snippet": {"channelId": "UCmine"}}]}, {"items": [hero]})
    f = prepare(fake, *responses, *responses, {"id": hero["id"]})
    f.client.set_playlist_cover("PLtest", image, apply=True)
    request = [r for r in f.requests if r.method == "PUT"][0]
    assert request.params.get("id") == hero["id"]
    assert "part" not in request.params and "other" not in request.params


def test_list_paginates_with_discovery_parent(fake):
    f = prepare(fake, {"items": [existing()], "nextPageToken": "next"}, {"items": []})
    assert f.client.list_playlist_images("PLtest") == [existing()]
    assert f.requests[1].params["pageToken"] == "next"


def test_wrong_owner_no_write(fake, image):
    f = prepare(fake, {"items": [{"snippet": {"channelId": "UCother"}}]})
    with pytest.raises(pc.PlaylistCoverError, match="another channel"):
        f.client.set_playlist_cover("PLtest", image, apply=True)
    assert all(r.method == "GET" for r in f.requests)


def test_invalid_and_non_square_images_fail_before_api(fake, image):
    f = prepare(fake)
    Image.new("RGB", (640, 360)).save(image)
    with pytest.raises(ValueError, match="square"):
        f.client.set_playlist_cover("PLtest", image, apply=True)
    image.write_bytes(b"not an image")
    with pytest.raises(ValueError, match="Invalid image"):
        f.client.set_playlist_cover("PLtest", image, apply=True)
    assert not f.requests


def test_stale_cover_and_permission_errors(fake, image):
    f = prepare(fake, *reads(True), *reads(False))
    plan = pc.plan_playlist_cover(f.client, "PLtest", image)
    with pytest.raises(pc.PlaylistCoverError, match="changed after planning"):
        pc.apply_playlist_cover(f.client, plan)
    assert all(r.method == "GET" for r in f.requests)
    failure = (403, {"error": {"code": 403, "message": "Refused"}})
    f = prepare(fake, *reads(), *reads(), failure)
    with pytest.raises(pc.PlaylistCoverError, match="HTTP 403.*eligibility"):
        f.client.set_playlist_cover("PLtest", image, apply=True)


def test_older_discovery_fails_with_upgrade_guidance(fake, image):
    f = prepare(fake)
    del f.client.youtube._rootDesc["resources"]["playlistImages"]
    with pytest.raises(pc.PlaylistCoverError, match="2.201.0"):
        f.client.set_playlist_cover("PLtest", image)
    assert not f.requests


def test_cover_cli_preview(fake, image, monkeypatch, capsys):
    f = prepare(fake, *reads())
    monkeypatch.setattr(cli, "client", lambda args: f.client)
    monkeypatch.setattr(sys, "argv", ["cover", "PLtest", "--image", str(image)])
    cli.main()
    assert "Dry run" in capsys.readouterr().out
    assert all(r.method == "GET" for r in f.requests)


@pytest.mark.parametrize("reason", ["invalidValue", "invalidPlaylistImage", "playlistForbidden", "quotaExceeded",
                                    "unexpectedPart", "unknownPart", "playlistImageNotFound", "imageTypeAlreadyExists"])
def test_refusal_exposes_only_recognized_reason_and_field(fake, image, reason):
    failure = (400, {"error": {"message": "PRIVATE_ERROR_SENTINEL",
        "errors": [{"reason": reason, "location": "snippet.type", "message": "PRIVATE_ERROR_SENTINEL"}]}})
    f = prepare(fake, *reads(False), *reads(False), failure)
    with pytest.raises(pc.PlaylistCoverError) as caught:
        f.client.set_playlist_cover("PLtest", image, apply=True)
    assert reason in str(caught.value)
    assert "snippet.type" in str(caught.value)
    assert "PRIVATE_ERROR_SENTINEL" not in str(caught.value)
    assert "HTTP 400" in str(caught.value)
    assert len([r for r in f.requests if r.method != "GET"]) == 1


@pytest.mark.parametrize("errors", [
    [{"reason": "PRIVATE_REASON_SENTINEL", "location": "PRIVATE_LOCATION_SENTINEL"}],
    [{"reason": ["invalidValue"], "location": {"field": "snippet.type"}}],
    [None, "bad"], None, "bad",
])
def test_unknown_or_malformed_refusal_details_stay_hidden(fake, image, errors):
    failure = (400, {"error": {"message": "PRIVATE_ERROR_SENTINEL", "errors": errors}})
    f = prepare(fake, *reads(False), *reads(False), failure)
    with pytest.raises(pc.PlaylistCoverError, match="HTTP 400") as caught:
        f.client.set_playlist_cover("PLtest", image, apply=True)
    assert "PRIVATE_" not in str(caught.value)
