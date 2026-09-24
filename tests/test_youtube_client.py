import pytest

from youtube3 import ChannelNotFoundException, YoutubeClient


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


CURRENT_STATUS = {
    "uploadStatus": "processed",
    "privacyStatus": "private",
    "license": "creativeCommon",
    "embeddable": False,
    "publicStatsViewable": False,
    "madeForKids": False,
    "selfDeclaredMadeForKids": False,
}


@pytest.mark.parametrize("status", ["private", "unlisted", "public"])
def test_update_status_sets_the_privacy_and_keeps_the_other_settings(fake, status):
    # videos.update resets every status field it is sent without (F-5).
    yt = fake({"items": [{"status": CURRENT_STATUS}]}, {"id": "vid1"})

    yt.client.update_status("vid1", status)

    read, update = yt.requests
    assert (read.path, read.params["part"]) == ("videos", "status")
    assert (update.method, update.path, update.params["part"]) == ("PUT", "videos", "status")
    assert update.body == {
        "id": "vid1",
        "status": {
            "privacyStatus": status,
            "license": "creativeCommon",
            "embeddable": False,
            "publicStatsViewable": False,
            "selfDeclaredMadeForKids": False,
        },
    }


def test_making_a_scheduled_video_public_drops_its_schedule(fake):
    scheduled = {**CURRENT_STATUS, "publishAt": "2030-01-01T00:00:00Z"}
    yt = fake({"items": [{"status": scheduled}]}, {"id": "vid1"})

    yt.client.update_status("vid1", "public")

    assert "publishAt" not in yt.requests[1].body["status"]


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


@pytest.mark.parametrize("max_count", [1, 2, "2"])
def test_iterate_videos_in_playlist_yields_at_most_max_count_pages(fake, max_count):
    yt = fake(
        playlist_page(["a"], next_token="t1"),
        playlist_page(["b"], next_token="t2"),
        playlist_page(["c"]),
    )

    pages = list(yt.client.iterate_videos_in_playlist("PL1", maxCount=max_count))

    assert len(pages) == int(max_count)
    assert len(yt.requests) == int(max_count)


def test_playlist_pages_ask_for_fifty_items(fake):
    yt = fake(playlist_page(["a"]))

    list(yt.client.iterate_videos_in_playlist("PL1"))

    assert yt.requests[0].params["maxResults"] == "50"


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


def test_delete_from_playlist_deletes_a_range_that_starts_later(fake):
    yt = fake(playlist_page(["a", "b", "c"]), (204, None), (204, None))

    yt.client.delete_from_playlist("PLsrc", 1, 3)

    assert [r.params["id"] for r in yt.requests[1:]] == ["item-b", "item-c"]


def test_copy_to_playlist_counts_positions_across_pages(fake):
    # Pages are fetched as the copy goes, so the requests interleave.
    yt = fake(
        playlist_page(["a", "b"], next_token="t1"),
        {"id": "new1"},
        playlist_page(["c", "d"]),
        {"id": "new2"},
    )

    yt.client.copy_to_playlist("PLsrc", "PLdst", 1, 3)

    assert [(r.method, r.params.get("pageToken")) for r in yt.requests] == [
        ("GET", None),
        ("POST", None),
        ("GET", "t1"),
        ("POST", None),
    ]
    inserts = [r for r in yt.requests if r.method == "POST"]
    assert [r.body["snippet"]["resourceId"]["videoId"] for r in inserts] == ["b", "c"]


def test_copy_to_playlist_stops_paging_after_the_range(fake):
    yt = fake(playlist_page(["a", "b"], next_token="t1"), {"id": "new1"})

    yt.client.copy_to_playlist("PLsrc", "PLdst", 0, 1)

    assert [(r.method, r.path) for r in yt.requests] == [("GET", "playlistItems"), ("POST", "playlistItems")]


def test_delete_from_playlist_logs_each_deleted_video(fake, caplog):
    yt = fake(playlist_page(["a", "b"]), (204, None), (204, None))

    with caplog.at_level("INFO", logger="youtube3"):
        yt.client.delete_from_playlist("PLsrc", 0, 2)

    removed = [r.getMessage() for r in caplog.records if r.getMessage().startswith("Removed")]
    assert removed == ["Removed video a from PLsrc", "Removed video b from PLsrc"]


# Subscriptions and likes


def test_iterate_subscriptions_follows_every_page_fifty_at_a_time(fake):
    def page(channel_ids, next_token=None):
        body = {
            "items": [
                {"snippet": {"resourceId": {"channelId": c}, "title": f"title {c}"}}
                for c in channel_ids
            ]
        }
        if next_token:
            body["nextPageToken"] = next_token
        return body

    yt = fake(page(["UC1"], next_token="t1"), page(["UC2"]))

    subscriptions = list(yt.client.iterate_subscriptions_in_channel())

    assert subscriptions == [{"id": "UC1", "title": "title UC1"}, {"id": "UC2", "title": "title UC2"}]
    assert [r.params.get("pageToken") for r in yt.requests] == [None, "t1"]
    assert {r.params["maxResults"] for r in yt.requests} == {"50"}
    assert {r.params["mine"] for r in yt.requests} == {"true"}


def test_liked_channel_is_the_likes_playlist(fake):
    yt = fake({"items": [{"contentDetails": {"relatedPlaylists": {"likes": "LL"}}}]})

    assert yt.client.liked_channel() == "LL"


def test_liked_channel_is_none_without_a_channel(fake):
    yt = fake({"items": []})

    assert yt.client.liked_channel() is None


def test_verify_video_is_false_when_the_api_fails(fake):
    yt = fake((500, {"error": {"code": 500, "message": "backend error"}}))

    assert yt.client.verify_video("vid1") is False


# Construction


def test_a_client_needs_secrets_or_a_service():
    with pytest.raises(ValueError):
        YoutubeClient()


def test_the_exception_is_an_ordinary_exception():
    assert issubclass(ChannelNotFoundException, Exception)


def test_copy_to_playlist_ending_on_a_page_boundary_fetches_no_further_page(fake):
    # Found by the v2.0.0 review (#16): end on the last item of a page.
    yt = fake(playlist_page(["a", "b"], next_token="t1"), {"id": "new1"}, {"id": "new2"})

    yt.client.copy_to_playlist("PLsrc", "PLdst", 0, 2)

    assert [r.method for r in yt.requests] == ["GET", "POST", "POST"]


def test_delete_from_playlist_ending_on_a_page_boundary_fetches_no_further_page(fake):
    yt = fake(playlist_page(["a", "b"], next_token="t1"), (204, None), (204, None))

    yt.client.delete_from_playlist("PLsrc", 0, 2)

    assert [r.method for r in yt.requests] == ["GET", "DELETE", "DELETE"]


@pytest.mark.parametrize("max_count", [None, 0, "0"])
def test_iterate_videos_in_playlist_without_a_limit_reads_every_page(fake, max_count):
    yt = fake(playlist_page(["a"], next_token="t1"), playlist_page(["b"]))

    pages = list(yt.client.iterate_videos_in_playlist("PL1", maxCount=max_count))

    assert len(pages) == 2


def test_verify_video_is_false_outside_the_allowed_countries(fake):
    yt = fake({"items": [{"contentDetails": {"regionRestriction": {"allowed": ["US", "CA"]}}}]})

    assert yt.client.verify_video("vid1", country="DE") is False


def test_verify_video_is_true_inside_the_allowed_countries(fake):
    yt = fake({"items": [{"contentDetails": {"regionRestriction": {"allowed": ["DE", "AT"]}}}]})

    assert yt.client.verify_video("vid1", country="DE") is True


def test_copy_to_playlist_without_apply_only_lists_the_range(fake):
    # Bulk writes get a dry run (#25).
    yt = fake(playlist_page(["a", "b", "c"]))

    assert yt.client.copy_to_playlist("PLsrc", "PLdst", 1, 3, apply=False) == ["b", "c"]
    assert [r.method for r in yt.requests] == ["GET"]


def test_delete_from_playlist_without_apply_only_lists_the_range(fake):
    yt = fake(playlist_page(["a", "b", "c"]))

    assert yt.client.delete_from_playlist("PLsrc", 0, 2, apply=False) == ["a", "b"]
    assert [r.method for r in yt.requests] == ["GET"]


def test_copy_and_delete_return_what_they_did(fake):
    yt = fake(playlist_page(["a"]), {"id": "new1"}, playlist_page(["a"]), (204, None))

    assert yt.client.copy_to_playlist("PLsrc", "PLdst", 0, 1) == ["a"]
    assert yt.client.delete_from_playlist("PLsrc", 0, 1) == ["a"]
