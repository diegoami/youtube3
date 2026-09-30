"""The videos uploaded to a channel: records and export."""

from datetime import datetime, timezone
from pathlib import Path

from .likes import write_json_atomically


def video_record(item, details):
    """One channel upload, from a playlistItems resource and its videos.list item.

    details is the matching videos.list resource (snippet, contentDetails,
    statistics, status), or None when the API no longer returns the video.
    """
    snippet = details.get("snippet", {}) if details else {}
    content = details.get("contentDetails", {}) if details else {}
    status = details.get("status", {}) if details else {}
    statistics = details.get("statistics", {}) if details else {}
    views = statistics.get("viewCount")
    return {
        "video_id": item["contentDetails"]["videoId"],
        "title": snippet.get("title") or item["snippet"].get("title"),
        "published_at": snippet.get("publishedAt") or item["snippet"].get("publishedAt"),
        "privacy": status.get("privacyStatus"),
        "views": int(views) if views is not None else None,
        "duration": content.get("duration"),
    }


def write_export(path, videos, now=None):
    """Write the channel's videos to path as JSON, and return how many there are."""
    path = Path(path)
    now = now or datetime.now(timezone.utc)
    write_json_atomically(
        path,
        {"exported_at": now.isoformat(timespec="seconds"), "count": len(videos), "videos": videos},
    )
    return len(videos)


def export_channel_videos(client, path, now=None):
    """Export every video uploaded to the client's channel to path, and return the count."""
    return write_export(path, list(client.iterate_channel_videos()), now)
