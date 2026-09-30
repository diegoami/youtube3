import json

import pytest

from youtube3 import ChannelNotFoundException, channel


def uploads(uploads_id):
    return {"items": [{"contentDetails": {"relatedPlaylists": {"uploads": uploads_id}}}]}


def playlist_page(entries, next_token=None):
    page = {
        "items": [
            {"contentDetails": {"videoId": video_id}, "snippet": {"title": title}}
            for video_id, title in entries
        ]
    }
    if next_token:
        page["nextPageToken"] = next_token
    return page


def details(video_id, title, published_at, privacy, views, duration):
    return {
        "id": video_id,
        "snippet": {"title": title, "publishedAt": published_at},
        "contentDetails": {"duration": duration},
        "statistics": {"viewCount": views},
        "status": {"privacyStatus": privacy},
    }


def test_uploads_playlist_reads_the_signed_in_channel(fake):
    yt = fake(uploads("UU1"))

    assert yt.client.uploads_playlist() == "UU1"

    [request] = yt.requests
    assert (request.path, request.params.get("mine"), request.params["part"]) == (
        "channels",
        "true",
        "contentDetails",
    )


def test_uploads_playlist_raises_when_the_channel_has_none(fake):
    yt = fake({"items": [{"contentDetails": {}}]})

    with pytest.raises(ChannelNotFoundException):
        yt.client.uploads_playlist()


def test_iterate_channel_videos_returns_one_record_per_upload(fake):
    yt = fake(
        uploads("UU1"),
        playlist_page([("v1", "First"), ("v2", "Second")]),
        {
            "items": [
                details("v1", "First", "2024-01-02T00:00:00Z", "public", "12", "PT4M13S"),
                details("v2", "Second", "2023-05-06T00:00:00Z", "unlisted", "0", "PT1H2M"),
            ]
        },
    )

    records = list(yt.client.iterate_channel_videos())

    assert records == [
        {
            "video_id": "v1",
            "title": "First",
            "published_at": "2024-01-02T00:00:00Z",
            "privacy": "public",
            "views": 12,
            "duration": "PT4M13S",
        },
        {
            "video_id": "v2",
            "title": "Second",
            "published_at": "2023-05-06T00:00:00Z",
            "privacy": "unlisted",
            "views": 0,
            "duration": "PT1H2M",
        },
    ]
    channels, listing, lookup = yt.requests
    assert listing.path == "playlistItems"
    assert listing.params["playlistId"] == "UU1"
    assert (lookup.path, lookup.params["id"]) == ("videos", "v1,v2")
    assert lookup.params["part"] == "snippet,contentDetails,statistics,status"


def test_iterate_channel_videos_pages_and_keeps_the_ids_together(fake):
    yt = fake(
        uploads("UU1"),
        playlist_page([("v1", "First")], next_token="NEXT"),
        {"items": [details("v1", "First", "2024-01-02T00:00:00Z", "public", "12", "PT4M13S")]},
        playlist_page([("v2", "Second")]),
        {"items": [details("v2", "Second", "2023-05-06T00:00:00Z", "private", "3", "PT1M")]},
    )

    records = list(yt.client.iterate_channel_videos())

    assert [record["video_id"] for record in records] == ["v1", "v2"]
    assert records[1]["privacy"] == "private"
    second_lookup = yt.requests[4]
    assert (second_lookup.path, second_lookup.params["id"]) == ("videos", "v2")


def test_write_export_saves_the_videos_and_the_count(tmp_path):
    videos = [{"video_id": "v1", "title": "First"}]
    path = tmp_path / "channel.json"

    assert channel.write_export(path, videos) == 1

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["count"] == 1
    assert saved["videos"] == videos
    assert saved["exported_at"]


def test_export_channel_videos_writes_what_the_client_yields(fake, tmp_path):
    yt = fake(
        uploads("UU1"),
        playlist_page([("v1", "First")]),
        {"items": [details("v1", "First", "2024-01-02T00:00:00Z", "public", "12", "PT4M13S")]},
    )
    path = tmp_path / "channel.json"

    assert channel.export_channel_videos(yt.client, path) == 1

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["videos"][0]["video_id"] == "v1"
    assert saved["videos"][0]["views"] == 12
