import json
from datetime import datetime, timezone

import pytest

from youtube3 import likes

NOW = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)


def liked_item(video_id, liked_at="2026-09-01T10:00:00Z", channel=("UC1", "Channel One"), title=None):
    snippet = {
        "title": title or f"title {video_id}",
        "publishedAt": liked_at,
        "resourceId": {"kind": "youtube#video", "videoId": video_id},
        "thumbnails": {
            "default": {"url": f"https://i.ytimg.com/vi/{video_id}/default.jpg"},
            "high": {"url": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"},
        },
        # The playlist's owner, not the video's: the record must not use these.
        "channelId": "UCme",
        "channelTitle": "Me",
    }
    if channel:
        snippet["videoOwnerChannelId"], snippet["videoOwnerChannelTitle"] = channel
    details = {"videoId": video_id}
    if channel:
        details["videoPublishedAt"] = "2020-01-01T00:00:00Z"
    return {"id": f"item-{video_id}", "snippet": snippet, "contentDetails": details}


def deleted_item(video_id):
    item = liked_item(video_id, channel=None, title="Deleted video")
    item["snippet"]["thumbnails"] = {}
    return item


def likes_page(items, next_token=None):
    page = {"items": items, "pageInfo": {"totalResults": len(items), "resultsPerPage": 50}}
    if next_token:
        page["nextPageToken"] = next_token
    return page


def record(video_id, liked_at="2026-09-01T10:00:00Z", channel_id="UC1", channel_title="Channel One", available=True):
    return {
        "video_id": video_id,
        "title": f"title {video_id}",
        "channel_id": channel_id,
        "channel_title": channel_title,
        "liked_at": liked_at,
        "published_at": "2020-01-01T00:00:00Z",
        "thumbnail": None,
        "available": available,
    }


def quota_exceeded():
    return (403, {"error": {"code": 403, "errors": [{"reason": "quotaExceeded"}], "message": "quota"}})


# Records


def test_a_liked_record_has_the_video_its_channel_and_when_it_was_liked():
    assert likes.liked_record(liked_item("v1", liked_at="2026-09-02T08:30:00Z")) == {
        "video_id": "v1",
        "title": "title v1",
        "channel_id": "UC1",
        "channel_title": "Channel One",
        "liked_at": "2026-09-02T08:30:00Z",
        "published_at": "2020-01-01T00:00:00Z",
        "thumbnail": "https://i.ytimg.com/vi/v1/hqdefault.jpg",
        "available": True,
    }


def test_a_deleted_video_is_kept_as_unavailable():
    assert likes.liked_record(deleted_item("gone")) == {
        "video_id": "gone",
        "title": "Deleted video",
        "channel_id": None,
        "channel_title": None,
        "liked_at": "2026-09-01T10:00:00Z",
        "published_at": None,
        "thumbnail": None,
        "available": False,
    }


def test_the_liked_videos_come_from_the_likes_playlist_page_by_page(fake):
    yt = fake(likes_page([liked_item("v1")], next_token="t1"), likes_page([deleted_item("v2")]))

    records = list(yt.client.iterate_liked_videos())

    assert [(r["video_id"], r["available"]) for r in records] == [("v1", True), ("v2", False)]
    assert [(r.params["playlistId"], r.params.get("pageToken")) for r in yt.requests] == [
        ("LL", None),
        ("LL", "t1"),
    ]


# Export


def test_the_export_holds_every_video_and_when_it_was_made(fake, tmp_path):
    yt = fake(likes_page([liked_item("v1"), liked_item("v2")]))
    path = tmp_path / "liked.json"

    change = likes.export_liked_videos(yt.client, path, now=NOW)

    export = json.loads(path.read_text(encoding="utf-8"))
    assert export["exported_at"] == "2026-09-24T12:00:00+00:00"
    assert export["count"] == 2
    assert [v["video_id"] for v in export["videos"]] == ["v1", "v2"]
    assert change == {"count": 2, "added": ["v1", "v2"], "removed": []}


def test_a_second_export_reports_what_was_added_and_removed(fake, tmp_path):
    path = tmp_path / "liked.json"
    likes.export_liked_videos(fake(likes_page([liked_item("v1"), liked_item("v2")])).client, path, now=NOW)

    change = likes.export_liked_videos(fake(likes_page([liked_item("v3"), liked_item("v1")])).client, path, now=NOW)

    assert change == {"count": 2, "added": ["v3"], "removed": ["v2"]}


def test_the_export_keeps_titles_in_their_own_script(fake, tmp_path):
    yt = fake(likes_page([liked_item("v1", title="Анна Плетнёва - Зима")]))
    path = tmp_path / "liked.json"

    likes.export_liked_videos(yt.client, path, now=NOW)

    assert "Анна Плетнёва - Зима" in path.read_text(encoding="utf-8")


def test_a_failed_export_leaves_the_previous_file_and_no_temporary_one(fake, tmp_path, monkeypatch):
    path = tmp_path / "liked.json"
    path.write_text('{"videos": []}', encoding="utf-8")

    def broken_dump(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(likes.json, "dump", broken_dump)
    with pytest.raises(OSError):
        likes.export_liked_videos(fake(likes_page([liked_item("v1")])).client, path, now=NOW)

    assert path.read_text(encoding="utf-8") == '{"videos": []}'
    assert [p.name for p in tmp_path.iterdir()] == ["liked.json"]


def test_unliked_videos_are_removed_from_the_export(tmp_path):
    path = tmp_path / "liked.json"
    path.write_text(json.dumps({"count": 3, "videos": [record("a"), record("b"), record("c")]}))

    likes.remove_from_export(path, ["b"])

    export = json.loads(path.read_text())
    assert [v["video_id"] for v in export["videos"]] == ["a", "c"]
    assert export["count"] == 2


def test_the_undo_log_records_what_was_rated_and_how(tmp_path):
    path = likes.write_undo_log(tmp_path, [record("a")], "none", now=NOW)

    assert path.name == "unliked-20260924-120000.json"
    log = json.loads(path.read_text())
    assert log["rating"] == "none"
    assert [v["video_id"] for v in log["videos"]] == ["a"]


# Selection

VIDEOS = [
    record("new", liked_at="2026-09-10T00:00:00Z", channel_id="UC1", channel_title="Channel One"),
    record("edge", liked_at="2020-01-01T00:00:00Z", channel_id="UC2", channel_title="Other"),
    record("old", liked_at="2019-12-31T23:59:59Z", channel_id="UC2", channel_title="Other"),
    record("gone", liked_at="2018-05-05T00:00:00Z", channel_id=None, channel_title=None, available=False),
]


def ids(videos):
    return [v["video_id"] for v in videos]


def test_no_criterion_selects_everything():
    assert ids(likes.select(VIDEOS)) == ["new", "edge", "old", "gone"]


@pytest.mark.parametrize("channel", ["UC2", "other", "OTHER"])
def test_select_by_channel_id_or_title_in_any_case(channel):
    assert ids(likes.select(VIDEOS, channel=channel)) == ["edge", "old"]


def test_liked_before_a_day_excludes_that_day():
    assert ids(likes.select(VIDEOS, liked_before="2020-01-01")) == ["old", "gone"]


def test_liked_after_a_day_includes_that_day():
    assert ids(likes.select(VIDEOS, liked_after="2020-01-01")) == ["new", "edge"]


def test_select_by_ids():
    assert ids(likes.select(VIDEOS, ids=["old", "missing"])) == ["old"]


def test_select_unavailable_or_available_only():
    assert ids(likes.select(VIDEOS, unavailable=True)) == ["gone"]
    assert ids(likes.select(VIDEOS, unavailable=False)) == ["new", "edge", "old"]


def test_criteria_combine():
    assert ids(likes.select(VIDEOS, channel="Other", liked_before="2020-01-01")) == ["old"]


# Rating in bulk


def test_a_dry_run_sends_nothing(fake):
    yt = fake()

    result = likes.unlike_videos(yt.client, ["a", "b"])

    assert yt.requests == []
    assert result["planned"] == ["a", "b"]
    assert result["done"] == []
    assert result["cost"] == 100


def test_the_limit_caps_a_run_and_duplicates_count_once(fake):
    yt = fake()

    result = likes.unlike_videos(yt.client, ["a", "b", "a", "c"], limit=2)

    assert result["planned"] == ["a", "b"]
    assert result["over_limit"] == ["c"]


def test_apply_rates_each_planned_video_none(fake):
    yt = fake((204, None), (204, None), (204, None))

    result = likes.unlike_videos(yt.client, ["a", "b", "c"], apply=True, limit=2)

    assert [(r.method, r.path, r.params["id"], r.params["rating"]) for r in yt.requests] == [
        ("POST", "videos/rate", "a", "none"),
        ("POST", "videos/rate", "b", "none"),
    ]
    assert result["done"] == ["a", "b"]


def test_a_run_stops_at_the_quota_and_reports_the_rest(fake):
    yt = fake((204, None), quota_exceeded(), (204, None))

    result = likes.unlike_videos(yt.client, ["a", "b", "c"], apply=True)

    assert result["done"] == ["a"]
    assert result["not_done"] == ["b", "c"]
    assert result["stopped"] == "quotaExceeded"
    assert len(yt.requests) == 2


def test_another_error_is_reported_and_the_run_goes_on(fake):
    not_found = (404, {"error": {"code": 404, "errors": [{"reason": "videoNotFound"}]}})
    yt = fake(not_found, (204, None))

    result = likes.unlike_videos(yt.client, ["gone", "b"], apply=True)

    assert result["failed"] == {"gone": "videoNotFound"}
    assert result["done"] == ["b"]


def test_relike_rates_like(fake):
    yt = fake((204, None))

    likes.like_videos(yt.client, ["a"], apply=True)

    assert yt.requests[0].params["rating"] == "like"


def test_an_unknown_rating_is_refused(fake):
    with pytest.raises(ValueError):
        likes.rate_videos(fake().client, ["a"], "dislike", apply=True)
