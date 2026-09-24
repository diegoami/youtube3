import json
from datetime import datetime, timezone

import pytest

from youtube3 import actions, history

NOW = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)


def watch(video_id, when, channel=("UC1", "Channel One"), removed=False):
    return {
        "video_id": None if removed else video_id,
        "title": f"title {video_id}",
        "channel_id": channel[0] if channel else None,
        "channel_title": channel[1] if channel else None,
        "watched_at": when,
        "removed": removed,
        "ad": False,
        "music": False,
    }


# Newest first, as history.json stores them.
HISTORY = [
    watch("a", "2026-09-22T08:00:00Z"),
    watch("b", "2026-09-21T09:00:00Z", channel=("UC2", "Déjà Vu")),
    watch("a", "2026-09-20T10:00:00Z"),
    watch("x", "2026-09-19T00:00:00Z", channel=None, removed=True),  # as Takeout has it: no link, no channel
    watch("a", "2026-01-01T00:00:00Z"),
    watch("c", "2019-12-31T23:59:59Z", channel=("UC2", "Déjà Vu")),
]


def ids(items, key="video_id"):
    return [item[key] for item in items]


def page(items, next_token=None):
    body = {"items": items}
    if next_token:
        body["nextPageToken"] = next_token
    return body


def playlist_item(video_id):
    return {"id": f"item-{video_id}", "contentDetails": {"videoId": video_id}}


def subscription(channel_id):
    return {"snippet": {"resourceId": {"channelId": channel_id}, "title": f"title {channel_id}"}}


QUOTA = (403, {"error": {"code": 403, "errors": [{"reason": "quotaExceeded"}]}})
DUPLICATE = (400, {"error": {"code": 400, "errors": [{"reason": "subscriptionDuplicate"}]}})


# Selection


def test_each_video_once_with_its_views_and_watches_newest_first():
    videos = history.watched_videos(HISTORY)

    assert ids(videos) == ["a", "b", "c"]
    a = videos[0]
    assert (a["views"], a["last_watched"], a["first_watched"]) == (3, "2026-09-22T08:00:00Z", "2026-01-01T00:00:00Z")


def test_the_removed_video_is_not_selectable():
    assert None not in ids(history.watched_videos(HISTORY))


@pytest.mark.parametrize("channel", ["UC2", "déjà vu", "DÉJÀ VU"])
def test_select_by_channel_id_or_title_in_any_case(channel):
    assert ids(history.select_watched(HISTORY, channel=channel)) == ["b", "c"]


def test_watched_after_includes_the_day_and_before_excludes_it():
    assert ids(history.select_watched(HISTORY, watched_after="2026-09-21")) == ["a", "b"]
    assert ids(history.select_watched(HISTORY, watched_before="2026-09-22")) == ["b", "c"]
    assert ids(history.select_watched(HISTORY, watched_before="2020-01-01")) == ["c"]


def test_select_by_views_ids_and_together():
    assert ids(history.select_watched(HISTORY, min_views=2)) == ["a"]
    assert ids(history.select_watched(HISTORY, ids=["c", "zzz"])) == ["c"]
    assert ids(history.select_watched(HISTORY, channel="UC2", watched_after="2026-01-01")) == ["b"]


def test_channels_are_ranked_by_watches():
    assert history.top_channels(HISTORY) == [
        {"channel_id": "UC1", "channel_title": "Channel One", "views": 3},
        {"channel_id": "UC2", "channel_title": "Déjà Vu", "views": 2},
    ]
    assert ids(history.top_channels(HISTORY, min_views=3), "channel_id") == ["UC1"]


# Like


def test_a_like_dry_run_sends_nothing_and_skips_what_is_liked(fake):
    yt = fake()
    videos = history.watched_videos(HISTORY)

    result = actions.like_watched(yt.client, videos, liked_ids={"b"})

    assert yt.requests == []
    assert result["planned"] == ["a", "c"]
    assert result["skipped"] == {"b": "already liked"}
    assert result["cost"] == 100


def test_like_rates_the_videos_like(fake):
    yt = fake((204, None), (204, None))

    result = actions.like_watched(yt.client, history.watched_videos(HISTORY), liked_ids={"b"}, apply=True)

    assert [(r.method, r.path, r.params["id"], r.params["rating"]) for r in yt.requests] == [
        ("POST", "videos/rate", "a", "like"),
        ("POST", "videos/rate", "c", "like"),
    ]
    assert result["done"] == ["a", "c"]


# Playlist


def test_adding_to_a_playlist_reads_it_first_and_skips_what_is_there(fake):
    yt = fake(page([playlist_item("a")]))

    result = actions.add_to_playlist(yt.client, history.watched_videos(HISTORY), playlist_id="PL1")

    [read] = yt.requests
    assert (read.method, read.path, read.params["playlistId"]) == ("GET", "playlistItems", "PL1")
    assert result["planned"] == ["b", "c"]
    assert result["skipped"] == {"a": "already in the playlist"}


def test_adding_to_a_playlist_inserts_and_records_the_items(fake):
    yt = fake(page([]), {"id": "new-b"}, {"id": "new-c"})
    videos = history.select_watched(HISTORY, channel="UC2")

    result = actions.add_to_playlist(yt.client, videos, playlist_id="PL1", apply=True)

    inserts = yt.requests[1:]
    assert [(r.method, r.path) for r in inserts] == [("POST", "playlistItems")] * 2
    assert [r.body["snippet"]["playlistId"] for r in inserts] == ["PL1", "PL1"]
    assert [r.body["snippet"]["resourceId"]["videoId"] for r in inserts] == ["b", "c"]
    assert result["created"] == {"b": "new-b", "c": "new-c"}
    assert result["new_playlist"] is False


def test_a_new_playlist_is_created_private_only_when_applied(fake):
    dry = fake()
    planned = actions.add_to_playlist(dry.client, history.watched_videos(HISTORY)[:2], new_title="Mine")
    assert dry.requests == []
    assert planned["cost"] == 150  # the playlist and two items

    yt = fake({"id": "PLnew"}, {"id": "new-a"}, {"id": "new-b"})
    result = actions.add_to_playlist(yt.client, history.watched_videos(HISTORY)[:2], new_title="Mine", apply=True)

    create = yt.requests[0]
    assert (create.method, create.path) == ("POST", "playlists")
    assert create.body == {"snippet": {"title": "Mine"}, "status": {"privacyStatus": "private"}}
    assert [r.body["snippet"]["playlistId"] for r in yt.requests[1:]] == ["PLnew", "PLnew"]
    assert (result["playlist_id"], result["new_playlist"]) == ("PLnew", True)


def test_a_playlist_needs_one_target(fake):
    with pytest.raises(ValueError):
        actions.add_to_playlist(fake().client, [], playlist_id="PL1", new_title="Mine")
    with pytest.raises(ValueError):
        actions.add_to_playlist(fake().client, [])


def test_a_run_stops_at_the_quota_and_reports_the_rest(fake):
    yt = fake(page([]), {"id": "new-a"}, QUOTA)

    result = actions.add_to_playlist(yt.client, history.watched_videos(HISTORY), playlist_id="PL1", apply=True)

    assert result["done"] == ["a"]
    assert result["not_done"] == ["b", "c"]
    assert result["stopped"] == "quotaExceeded"


# Subscribe


def test_a_subscribe_dry_run_only_reads_and_skips_what_is_subscribed(fake):
    yt = fake(page([subscription("UC1")]))

    result = actions.subscribe_to(yt.client, history.top_channels(HISTORY))

    assert [r.method for r in yt.requests] == ["GET"]
    assert result["planned"] == ["UC2"]
    assert result["skipped"] == {"UC1": "already subscribed"}


def test_subscribing_records_each_subscription(fake):
    yt = fake(page([]), {"id": "sub-1"}, {"id": "sub-2"})

    result = actions.subscribe_to(yt.client, history.top_channels(HISTORY), apply=True)

    posts = yt.requests[1:]
    assert [r.body["snippet"]["resourceId"]["channelId"] for r in posts] == ["UC1", "UC2"]
    assert result["created"] == {"UC1": "sub-1", "UC2": "sub-2"}
    assert result["done"] == ["UC1", "UC2"]


def test_a_duplicate_subscription_is_skipped_not_done(fake):
    yt = fake(page([]), DUPLICATE, {"id": "sub-2"})

    result = actions.subscribe_to(yt.client, history.top_channels(HISTORY), apply=True)

    assert result["done"] == ["UC2"]
    assert result["skipped"] == {"UC1": "already subscribed"}
    assert result["failed"] == {}


# Logs and undo


def test_the_log_records_what_was_created(tmp_path, fake):
    videos = history.select_watched(HISTORY, channel="UC2")
    result = actions.add_to_playlist(fake(page([]), {"id": "new-b"}, {"id": "new-c"}).client, videos, playlist_id="PL1", apply=True)

    path = actions.write_action_log(tmp_path, "playlist", videos, result, now=NOW)

    assert path.name == "history-playlist-20260924-120000.json"
    log = json.loads(path.read_text())
    assert (log["action"], log["playlist_id"], log["new_playlist"]) == ("playlist", "PL1", False)
    assert [(v["video_id"], v["created"]) for v in log["done"]] == [("b", "new-b"), ("c", "new-c")]


def test_two_logs_in_the_same_second_are_both_kept(tmp_path):
    result = {"done": ["a"], "created": {}}
    first = actions.write_action_log(tmp_path, "like", [{"video_id": "a"}], result, now=NOW)
    second = actions.write_action_log(tmp_path, "like", [{"video_id": "a"}], result, now=NOW)

    assert first != second and second.name.endswith("-2.json")


def test_undo_like_unlikes(fake):
    yt = fake((204, None))

    actions.undo_actions(yt.client, {"action": "like", "done": [{"video_id": "a", "created": None}]}, apply=True)

    assert (yt.requests[0].path, yt.requests[0].params["rating"]) == ("videos/rate", "none")


def test_undo_playlist_deletes_the_items_it_added(fake):
    yt = fake((204, None))
    log = {"action": "playlist", "playlist_id": "PL1", "new_playlist": False, "done": [{"video_id": "b", "created": "new-b"}]}

    actions.undo_actions(yt.client, log, apply=True)

    assert [(r.method, r.path, r.params["id"]) for r in yt.requests] == [("DELETE", "playlistItems", "new-b")]


def test_undo_a_new_playlist_deletes_the_playlist(fake):
    yt = fake((204, None))
    log = {"action": "playlist", "playlist_id": "PLnew", "new_playlist": True, "done": [{"video_id": "b", "created": "new-b"}]}

    actions.undo_actions(yt.client, log, apply=True)

    assert [(r.method, r.path, r.params["id"]) for r in yt.requests] == [("DELETE", "playlists", "PLnew")]


def test_undo_subscribe_unsubscribes(fake):
    yt = fake((204, None))

    actions.undo_actions(yt.client, {"action": "subscribe", "done": [{"channel_id": "UC1", "created": "sub-1"}]}, apply=True)

    assert [(r.method, r.path, r.params["id"]) for r in yt.requests] == [("DELETE", "subscriptions", "sub-1")]


def test_an_undo_dry_run_sends_nothing(fake):
    yt = fake()

    result = actions.undo_actions(yt.client, {"action": "subscribe", "done": [{"channel_id": "UC1", "created": "sub-1"}]})

    assert yt.requests == [] and result["planned"] == ["UC1"]


def test_an_unknown_log_is_refused(fake):
    with pytest.raises(ValueError):
        actions.undo_actions(fake().client, {"action": "rate", "done": []})


def test_the_day_bounds_are_exact_at_midnight():
    midnight = [watch("m", "2026-09-21T00:00:00Z")]

    assert ids(history.select_watched(midnight, watched_after="2026-09-21")) == ["m"]
    assert ids(history.select_watched(midnight, watched_before="2026-09-21")) == []
    assert ids(history.select_watched(midnight, watched_before="2026-09-22")) == ["m"]
