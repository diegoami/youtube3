import struct
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from youtube3 import publish

REAL_JPEG = Path(__file__).parent / "data" / "real-1280x720.jpg"
NOW = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)

SNIPPET = {
    "title": "Old title",
    "description": "Old description",
    "tags": ["one", "two"],
    "categoryId": "10",
    "defaultLanguage": "en",
    # Read-only fields the API returns: they must never be sent back.
    "channelId": "UCme",
    "channelTitle": "Me",
    "publishedAt": "2026-09-20T10:00:00Z",
    "thumbnails": {"default": {"url": "x"}},
    "localized": {"title": "Old title"},
    "liveBroadcastContent": "none",
}
STATUS = {
    "uploadStatus": "processed",
    "privacyStatus": "private",
    "license": "youtube",
    "embeddable": False,
    "publicStatsViewable": True,
    "madeForKids": False,
    "selfDeclaredMadeForKids": False,
}


def video(snippet=None, status=None):
    return {"items": [{"id": "vid1", "snippet": snippet or SNIPPET, "status": status or STATUS}]}


def channel(long_uploads="allowed"):
    """The channel's status: custom thumbnails need it "allowed" (a verified channel)."""
    return {"items": [{"status": {"longUploadsStatus": long_uploads}}]}


def png(path, width, height, padding=0):
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + ihdr + b"\0" * (4 + padding))
    return path


def segment(marker, payload):
    return bytes([0xFF, marker]) + struct.pack(">H", len(payload) + 2) + payload


def jpeg(path, width, height, frame=0xC0, before=b""):
    sof = segment(frame, struct.pack(">BHHB", 8, height, width, 3) + b"\x01\x22\x00" * 3)
    path.write_bytes(b"\xff\xd8" + segment(0xE0, b"JFIF\0\x01\x01\0\0\x01\0\x01\0\0") + before + sof + b"\xff\xd9")
    return path


# Thumbnails


def test_a_real_jpeg_from_an_encoder_is_read():
    assert publish.image_type_and_size(REAL_JPEG) == ("image/jpeg", 1280, 720)
    report = publish.check_thumbnail(REAL_JPEG)
    assert (report["errors"], report["warnings"]) == ([], [])


def test_a_png_is_read(tmp_path):
    assert publish.image_type_and_size(png(tmp_path / "t.png", 1920, 1080)) == ("image/png", 1920, 1080)


@pytest.mark.parametrize(
    "before",
    [
        segment(0xE1, b"Exif\0\0" + b"\0" * 300),  # metadata before the frame
        segment(0xC4, b"\0" * 20),  # a Huffman table: C4 is not a frame
        b"\xff\xff\xff",  # fill bytes before the next marker
    ],
)
def test_a_jpeg_frame_is_found_past_other_segments(tmp_path, before):
    assert publish.image_type_and_size(jpeg(tmp_path / "t.jpg", 1280, 720, before=before)) == ("image/jpeg", 1280, 720)


def test_a_progressive_jpeg_is_read(tmp_path):
    assert publish.image_type_and_size(jpeg(tmp_path / "t.jpg", 800, 450, frame=0xC2))[1:] == (800, 450)


def test_a_truncated_jpeg_is_reported(tmp_path):
    path = tmp_path / "t.jpg"
    path.write_bytes(b"\xff\xd8\xff\xe0\x00\x10JFIF")

    assert publish.check_thumbnail(path)["errors"] == ["the image size could not be read"]


def test_a_file_named_like_an_image_is_judged_by_its_bytes(tmp_path):
    path = tmp_path / "fake.jpg"
    path.write_text("GIF89a, not a JPEG")

    assert publish.check_thumbnail(path)["errors"] == ["not a PNG or JPEG image"]


def test_a_thumbnail_over_2_mb_is_refused(tmp_path):
    report = publish.check_thumbnail(png(tmp_path / "big.png", 1280, 720, padding=2 * 1024 * 1024))

    assert any("at most 2 MB" in error for error in report["errors"])


def test_a_thumbnail_narrower_than_640_is_refused_and_a_small_one_warned(tmp_path):
    narrow = publish.check_thumbnail(png(tmp_path / "n.png", 600, 338))
    small = publish.check_thumbnail(png(tmp_path / "s.png", 640, 360))

    assert narrow["errors"] == ["600 px wide: YouTube needs at least 640"]
    assert small["errors"] == [] and small["warnings"] == ["640×360 is below the recommended 1280×720"]


def test_a_thumbnail_that_is_not_16_9_is_warned(tmp_path):
    report = publish.check_thumbnail(png(tmp_path / "sq.png", 1280, 1280))

    assert report["errors"] == [] and "not 16:9" in report["warnings"][0]


def test_a_missing_thumbnail_is_refused(tmp_path):
    assert publish.check_thumbnail(tmp_path / "none.png")["errors"] == ["no such file"]


# Planning


def test_a_plan_reads_the_video_once_and_writes_nothing(fake):
    yt = fake(video())

    plan = publish.plan_publish(yt.client, "vid1", title="New title", now=NOW)

    [request] = yt.requests
    assert (request.method, request.path, request.params["part"]) == ("GET", "videos", "snippet,status")
    assert plan["changes"] == {"title": ("Old title", "New title")}
    assert plan["errors"] == []
    assert plan["cost"] == 50


def test_the_planned_snippet_is_whole_and_writable_only(fake):
    plan = publish.plan_publish(fake(video()).client, "vid1", title="New title", now=NOW)

    assert plan["snippet"] == {
        "title": "New title",
        "description": "Old description",
        "tags": ["one", "two"],
        "categoryId": "10",
        "defaultLanguage": "en",
    }
    assert plan["status"] is None


def test_nothing_to_change_costs_nothing(fake):
    plan = publish.plan_publish(fake(video()).client, "vid1", title="Old title", now=NOW)

    assert (plan["changes"], plan["snippet"], plan["status"], plan["cost"]) == ({}, None, None, 0)


def test_tags_are_trimmed_and_blank_ones_dropped(fake):
    plan = publish.plan_publish(fake(video()).client, "vid1", tags=[" a ", "", "b"], now=NOW)

    assert plan["snippet"]["tags"] == ["a", "b"]


@pytest.mark.parametrize(
    "fields, error",
    [
        ({"title": ""}, "1 to 100 characters"),
        ({"title": "x" * 101}, "1 to 100 characters"),
        ({"title": "a <b> title"}, "< or > in a title"),
        ({"description": "é" * 2501}, "over 5000 bytes"),
        ({"description": "see <here>"}, "< or > in a description"),
        ({"tags": ["x" * 300, "y" * 201]}, "over 500 characters"),
        ({"privacy": "friends"}, "privacy must be one of"),
        ({"publish_at": "2026-09-24T11:00:00+00:00"}, "not in the future"),
        ({"publish_at": "2026-10-01T18:00:00+00:00", "privacy": "public"}, "stays private until its time"),
    ],
)
def test_invalid_changes_are_refused_before_anything_is_sent(fake, fields, error):
    plan = publish.plan_publish(fake(video()).client, "vid1", now=NOW, **fields)

    assert any(error in message for message in plan["errors"]), plan["errors"]


def test_a_description_of_exactly_5000_bytes_is_allowed(fake):
    plan = publish.plan_publish(fake(video()).client, "vid1", description="é" * 2500, now=NOW)

    assert plan["errors"] == []


def test_scheduling_keeps_the_video_private_until_then_in_utc(fake):
    plan = publish.plan_publish(fake(video()).client, "vid1", publish_at="2026-10-01T18:00:00+02:00", now=NOW)

    assert plan["errors"] == []
    assert plan["status"]["privacyStatus"] == "private"
    assert plan["status"]["publishAt"] == "2026-10-01T16:00:00Z"
    # The rest of the status is sent back unchanged.
    assert plan["status"]["embeddable"] is False and plan["status"]["license"] == "youtube"
    assert "uploadStatus" not in plan["status"] and "madeForKids" not in plan["status"]


@pytest.mark.skipif(not hasattr(time, "tzset"), reason="time.tzset is POSIX only")
def test_a_time_without_an_offset_is_local_time(fake, monkeypatch):
    monkeypatch.setenv("TZ", "Europe/Berlin")
    time.tzset()
    try:
        plan = publish.plan_publish(fake(video()).client, "vid1", publish_at="2026-10-01T18:00", now=NOW)
    finally:
        monkeypatch.undo()
        time.tzset()

    assert plan["status"]["publishAt"] == "2026-10-01T16:00:00Z"


def test_an_unlisted_video_can_be_scheduled_and_becomes_private_until_then(fake):
    plan = publish.plan_publish(
        fake(video(status={**STATUS, "privacyStatus": "unlisted"})).client,
        "vid1",
        publish_at="2026-10-01T16:00:00Z",
        now=NOW,
    )

    assert plan["errors"] == []
    assert plan["changes"]["privacyStatus"] == ("unlisted", "private")


def test_a_public_video_cannot_be_scheduled(fake):
    plan = publish.plan_publish(
        fake(video(status={**STATUS, "privacyStatus": "public"})).client,
        "vid1",
        publish_at="2026-10-01T16:00:00Z",
        now=NOW,
    )

    assert any("already public" in error for error in plan["errors"])


def test_publishing_now_drops_a_schedule(fake):
    scheduled = {**STATUS, "publishAt": "2026-10-01T16:00:00Z"}
    plan = publish.plan_publish(fake(video(status=scheduled)).client, "vid1", privacy="public", now=NOW)

    assert plan["status"]["privacyStatus"] == "public"
    assert "publishAt" not in plan["status"]
    assert plan["changes"]["publishAt"] == ("2026-10-01T16:00:00Z", None)


def test_an_unknown_video_is_refused(fake):
    with pytest.raises(publish.PublishError):
        publish.plan_publish(fake({"items": []}).client, "nope", title="x", now=NOW)


def test_a_bad_thumbnail_is_an_error_of_the_plan(fake, tmp_path):
    plan = publish.plan_publish(fake(video(), channel()).client, "vid1", thumbnail=tmp_path / "none.png", now=NOW)

    assert plan["errors"] == ["thumbnail: no such file"]


# Applying


def test_apply_sends_one_update_with_whole_parts_then_the_thumbnail(fake):
    yt = fake(video(), channel(), {"id": "vid1"}, {"items": []})
    plan = publish.plan_publish(
        yt.client, "vid1", title="New title", thumbnail=REAL_JPEG, publish_at="2026-10-01T16:00:00Z", now=NOW
    )

    done = publish.apply_publish(yt.client, plan)

    _, _, update, thumbnail = yt.requests
    assert (update.method, update.path, update.params["part"]) == ("PUT", "videos", "snippet,status")
    assert update.body["id"] == "vid1"
    assert update.body["snippet"]["tags"] == ["one", "two"]
    assert update.body["status"]["publishAt"] == "2026-10-01T16:00:00Z"
    assert update.body["status"]["embeddable"] is False
    assert (thumbnail.method, thumbnail.path, thumbnail.params["videoId"]) == ("POST", "thumbnails/set", "vid1")
    assert thumbnail.headers["content-type"] == "image/jpeg"
    assert thumbnail.raw == REAL_JPEG.read_bytes()
    assert done == ["snippet", "status", "thumbnail"]


def test_a_thumbnail_alone_sends_no_update(fake):
    yt = fake(video(), channel(), {"items": []})
    plan = publish.plan_publish(yt.client, "vid1", thumbnail=REAL_JPEG, now=NOW)

    assert publish.apply_publish(yt.client, plan) == ["thumbnail"]
    assert [r.path for r in yt.requests] == ["videos", "channels", "thumbnails/set"]
    assert plan["cost"] == 50


def test_a_plan_with_errors_is_not_applied(fake):
    yt = fake(video())
    plan = publish.plan_publish(yt.client, "vid1", title="", now=NOW)

    with pytest.raises(publish.PublishError):
        publish.apply_publish(yt.client, plan)
    assert len(yt.requests) == 1


def test_upload_thumbnail_sends_the_file_with_its_media_type(fake, tmp_path):
    yt = fake({"items": []})
    path = png(tmp_path / "t.png", 1280, 720)

    yt.client.upload_thumbnail("vid1", str(path))

    [request] = yt.requests
    assert request.headers["content-type"] == "image/png"
    assert request.raw == path.read_bytes()


@pytest.mark.parametrize("name", ["thumbnail", "really-a-png.jpg"])
def test_the_media_type_comes_from_the_bytes_not_the_name(fake, tmp_path, name):
    yt = fake({"items": []})
    path = png(tmp_path / name, 1280, 720)

    yt.client.upload_thumbnail("vid1", str(path))

    assert yt.requests[0].headers["content-type"] == "image/png"


@pytest.mark.parametrize("length", range(16, 24))
def test_a_truncated_png_is_reported_not_a_crash(tmp_path, length):
    # #44: a PNG cut inside its IHDR raised struct.error.
    path = tmp_path / "t.png"
    path.write_bytes(png(tmp_path / "full.png", 1280, 720).read_bytes()[:length])

    assert publish.check_thumbnail(path)["errors"] == ["the image size could not be read"]


# From G5 of milestone v2.5.0 (#49)


@pytest.mark.parametrize("status", ["eligible", "disallowed", None])
def test_a_thumbnail_on_an_unverified_channel_is_refused_before_any_write(fake, status):
    yt = fake(video(), channel(status))

    plan = publish.plan_publish(yt.client, "vid1", title="New title", thumbnail=REAL_JPEG, now=NOW)

    assert any("verified channel" in error and "youtube.com/verify" in error for error in plan["errors"])
    with pytest.raises(publish.PublishError):
        publish.apply_publish(yt.client, plan)
    assert [r.method for r in yt.requests] == ["GET", "GET"]
    assert yt.requests[1].params == {"part": "status", "mine": "true", "key": "test-key", "alt": "json"}


def test_no_thumbnail_means_no_channel_read(fake):
    yt = fake(video())

    publish.plan_publish(yt.client, "vid1", title="New title", now=NOW)

    assert [r.path for r in yt.requests] == ["videos"]


def test_a_thumbnail_refused_after_the_update_says_what_was_done(fake):
    refused = (403, {"error": {"code": 403, "errors": [{"reason": "forbidden", "message": "no permission"}]}})
    yt = fake(video(), channel(), {"id": "vid1"}, refused)
    plan = publish.plan_publish(yt.client, "vid1", title="New title", thumbnail=REAL_JPEG, now=NOW)

    with pytest.raises(publish.PublishError) as refusal:
        publish.apply_publish(yt.client, plan)

    assert refusal.value.done == ["snippet"]
    assert "snippet" in str(refusal.value) and "thumbnail" in str(refusal.value) and "forbidden" in str(refusal.value)
