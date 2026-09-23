import pytest

from youtube3 import ChannelNotFoundException


def playlist_page(video_ids, next_token=None, item_prefix="item"):
    page = {
        "items": [
            {"id": f"{item_prefix}-{v}", "contentDetails": {"videoId": v}} for v in video_ids
        ]
    }
    if next_token:
        page["nextPageToken"] = next_token
    return page


# Channels and videos


def test_get_channel_name_fetches_once_then_uses_the_cache(fake):
    yt = fake({"items": [{"snippet": {"title": "Channel One"}}]})

    assert yt.client.get_channel_name("UC1") == "Channel One"
    assert yt.client.get_channel_name("UC1") == "Channel One"

    [request] = yt.requests
    assert request.path == "channels"
    assert request.params["id"] == "UC1"
    assert request.params["part"] == "snippet"


def test_get_channel_snippet_raises_for_an_unknown_channel(fake):
    yt = fake({"items": []})

    with pytest.raises(ChannelNotFoundException):
        yt.client.get_channel_snippet("UCmissing")


def test_get_video_snippet_returns_the_first_item(fake):
    yt = fake({"items": [{"snippet": {"title": "A video", "channelId": "UC1"}}]})

    assert yt.client.get_video_snippet("vid1") == {"title": "A video", "channelId": "UC1"}
    assert yt.requests[0].params == {"id": "vid1", "part": "snippet", "key": "test-key", "alt": "json"}


def test_get_channel_id_returns_the_video_channel(fake):
    yt = fake({"items": [{"snippet": {"channelId": "UC1"}}]})

    assert yt.client.get_channel_id("vid1") == "UC1"


def test_get_channel_id_raises_for_an_unknown_video(fake):
    yt = fake({"items": []})

    with pytest.raises(ChannelNotFoundException):
        yt.client.get_channel_id("missing")


def test_like_video_rates_it_like(fake):
    yt = fake((204, None))

    yt.client.like_video("vid1")

    [request] = yt.requests
    assert (request.method, request.path) == ("POST", "videos/rate")
    assert request.params["id"] == "vid1"
    assert request.params["rating"] == "like"


def test_update_snippet_sends_the_id_and_the_snippet(fake):
    yt = fake({"id": "vid1"})
    snippet = {"title": "New title", "categoryId": "10"}

    yt.client.update_snippet("vid1", snippet)

    [request] = yt.requests
    assert (request.method, request.path) == ("PUT", "videos")
    assert request.params["part"] == "snippet"
    assert request.body == {"id": "vid1", "snippet": snippet}


@pytest.mark.parametrize("status", ["private", "unlisted", "public"])
def test_update_status_sets_the_privacy(fake, status):
    yt = fake({"id": "vid1"})

    yt.client.update_status("vid1", status)

    [request] = yt.requests
    assert (request.method, request.path) == ("PUT", "videos")
    assert request.params["part"] == "status"
    assert request.body == {"id": "vid1", "status": {"privacyStatus": status}}


def test_update_status_rejects_an_unknown_privacy_without_calling_the_api(fake):
    yt = fake()

    with pytest.raises(ValueError):
        yt.client.update_status("vid1", "friends-only")

    assert yt.requests == []


def test_subscribe_channel_sends_the_channel_id(fake):
    yt = fake({"id": "sub1"})

    yt.client.subscribe_channel("UC1")

    [request] = yt.requests
    assert (request.method, request.path) == ("POST", "subscriptions")
    assert request.body == {"snippet": {"resourceId": {"channelId": "UC1"}}}


# Region check


def test_verify_video_is_false_when_blocked_in_the_country(fake):
    yt = fake({"items": [{"contentDetails": {"regionRestriction": {"blocked": ["DE", "AT"]}}}]})

    assert yt.client.verify_video("vid1", country="DE") is False


def test_verify_video_is_true_when_blocked_only_elsewhere(fake):
    yt = fake({"items": [{"contentDetails": {"regionRestriction": {"blocked": ["US"]}}}]})

    assert yt.client.verify_video("vid1", country="DE") is True


def test_verify_video_is_false_for_a_missing_video(fake):
    yt = fake({"items": []})

    assert yt.client.verify_video("gone") is False


# Playlists


def test_playlist_name_is_the_localized_title(fake):
    yt = fake({"items": [{"snippet": {"localized": {"title": "Favourites"}}}]})

    assert yt.client.playlist_name("PL1") == "Favourites"


def test_playlist_name_is_none_for_an_unknown_playlist(fake):
    yt = fake({"items": []})

    assert yt.client.playlist_name("PLmissing") is None


def test_iterate_videos_in_playlist_follows_every_page(fake):
    yt = fake(
        playlist_page(["a", "b"], next_token="t1"),
        playlist_page(["c"], next_token="t2"),
        playlist_page(["d"]),
    )

    pages = list(yt.client.iterate_videos_in_playlist("PL1"))

    assert [i["contentDetails"]["videoId"] for p in pages for i in p["items"]] == ["a", "b", "c", "d"]
    assert [r.params.get("pageToken") for r in yt.requests] == [None, "t1", "t2"]
    assert {r.params["playlistId"] for r in yt.requests} == {"PL1"}


def test_iterate_videos_in_playlist_max_count_current_behaviour(fake):
    # Pins what the code does today: maxCount=1 yields two pages, not one.
    yt = fake(
        playlist_page(["a"], next_token="t1"),
        playlist_page(["b"], next_token="t2"),
        playlist_page(["c"]),
    )

    pages = list(yt.client.iterate_videos_in_playlist("PL1", maxCount=1))

    assert len(pages) == 2
    assert len(yt.requests) == 2


def test_copy_to_playlist_inserts_the_range_from_the_start(fake):
    yt = fake(playlist_page(["a", "b", "c"]), {"id": "new1"}, {"id": "new2"})

    yt.client.copy_to_playlist("PLsrc", "PLdst", 0, 2)

    list_request, *inserts = yt.requests
    assert list_request.params["playlistId"] == "PLsrc"
    assert [(r.method, r.path) for r in inserts] == [("POST", "playlistItems")] * 2
    assert [r.body for r in inserts] == [
        {
            "snippet": {
                "playlistId": "PLdst",
                "resourceId": {"kind": "youtube#video", "videoId": video_id},
            }
        }
        for video_id in ["a", "b"]
    ]


@pytest.mark.xfail(reason="the range counter only moves inside the range; F-2 fixes it")
def test_copy_to_playlist_inserts_a_range_that_starts_later(fake):
    yt = fake(playlist_page(["a", "b", "c"]), {"id": "new1"}, {"id": "new2"})

    yt.client.copy_to_playlist("PLsrc", "PLdst", 1, 3)

    inserted = [r.body["snippet"]["resourceId"]["videoId"] for r in yt.requests[1:]]
    assert inserted == ["b", "c"]


def test_delete_from_playlist_deletes_the_range_from_the_start(fake):
    yt = fake(playlist_page(["a", "b", "c"]), (204, None), (204, None))

    yt.client.delete_from_playlist("PLsrc", 0, 2)

    list_request, *deletes = yt.requests
    assert list_request.params["playlistId"] == "PLsrc"
    assert [(r.method, r.path, r.params["id"]) for r in deletes] == [
        ("DELETE", "playlistItems", "item-a"),
        ("DELETE", "playlistItems", "item-b"),
    ]


@pytest.mark.xfail(reason="the range counter only moves inside the range; F-2 fixes it")
def test_delete_from_playlist_deletes_a_range_that_starts_later(fake):
    yt = fake(playlist_page(["a", "b", "c"]), (204, None), (204, None))

    yt.client.delete_from_playlist("PLsrc", 1, 3)

    assert [r.params["id"] for r in yt.requests[1:]] == ["item-b", "item-c"]
