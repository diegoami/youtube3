"""The liked videos: records, export, selection, and rating in bulk."""

import json
import logging
import os
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

from googleapiclient.errors import HttpError

logger = logging.getLogger("youtube3")

# The authenticated user's "Liked videos" playlist.
LIKES_PLAYLIST = "LL"
# Quota units per videos.rate call, out of a default 10,000 a day.
RATE_COST = 50
DAILY_QUOTA = 10_000
# Enough for one run to fit in a day's quota with room for listing.
DEFAULT_LIMIT = 150

THUMBNAIL_SIZES = ("maxres", "standard", "high", "medium", "default")


def liked_record(item):
    """One liked video, from a playlistItems resource of the likes playlist.

    Deleted and private videos stay in the playlist without their channel;
    they are kept, with available set to False.
    """
    snippet = item["snippet"]
    details = item.get("contentDetails", {})
    thumbnails = snippet.get("thumbnails") or {}
    thumbnail = next((thumbnails[size]["url"] for size in THUMBNAIL_SIZES if size in thumbnails), None)
    return {
        "video_id": details.get("videoId") or snippet["resourceId"]["videoId"],
        # The entry in the likes playlist: how an unavailable video is removed.
        "item_id": item.get("id"),
        "title": snippet.get("title"),
        "channel_id": snippet.get("videoOwnerChannelId"),
        "channel_title": snippet.get("videoOwnerChannelTitle"),
        # For the likes playlist, the time the item was added is the time of the like.
        "liked_at": snippet.get("publishedAt"),
        "published_at": details.get("videoPublishedAt"),
        "thumbnail": thumbnail,
        "available": "videoOwnerChannelId" in snippet,
    }


# Export


def load_export(path):
    with open(path, encoding="utf-8") as export:
        return json.load(export)


def write_json_atomically(path, data):
    """Write data as UTF-8 JSON; a failure leaves the previous file untouched."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(data, output, ensure_ascii=False, indent=1)
        os.replace(temporary, path)
    except BaseException:
        os.unlink(temporary)
        raise


def export_liked_videos(client, path, now=None):
    """Export every liked video to path, newest like first.

    Returns the count and the ids added and removed since the file's previous
    contents (none when there was no previous file).
    """
    path = Path(path)
    previous = load_export(path)["videos"] if path.exists() else []
    videos = list(client.iterate_liked_videos())
    now = now or datetime.now(timezone.utc)
    write_json_atomically(
        path,
        {"exported_at": now.isoformat(timespec="seconds"), "count": len(videos), "videos": videos},
    )
    before = {video["video_id"] for video in previous}
    after = {video["video_id"] for video in videos}
    return {
        "count": len(videos),
        "added": [video["video_id"] for video in videos if video["video_id"] not in before],
        "removed": [video["video_id"] for video in previous if video["video_id"] not in after],
    }


def remove_from_export(path, video_ids):
    """Drop video_ids from an export, after they were unliked."""
    export = load_export(path)
    gone = set(video_ids)
    export["videos"] = [video for video in export["videos"] if video["video_id"] not in gone]
    export["count"] = len(export["videos"])
    write_json_atomically(path, export)


def write_undo_log(folder, records, rating, now=None):
    """Save what a run changed, so it can be replayed the other way."""
    now = now or datetime.now(timezone.utc)
    prefix = "unliked" if rating == "none" else "reliked"
    stem = f"{prefix}-{now.strftime('%Y%m%d-%H%M%S')}"
    path = Path(folder) / f"{stem}.json"
    # Two runs in the same second must not replace each other's log.
    counter = 2
    while path.exists():
        path = Path(folder) / f"{stem}-{counter}.json"
        counter += 1
    write_json_atomically(
        path, {"rated_at": now.isoformat(timespec="seconds"), "rating": rating, "videos": records}
    )
    return path


# Selection


def _day_start(day):
    if isinstance(day, str):
        day = date.fromisoformat(day)
    if isinstance(day, datetime):
        return day if day.tzinfo else day.replace(tzinfo=timezone.utc)
    return datetime(day.year, day.month, day.day, tzinfo=timezone.utc)


def select(videos, channel=None, liked_before=None, liked_after=None, ids=None, unavailable=None):
    """The videos matching every criterion given; no criterion matches all.

    channel: a channel id, or a channel title in any case. liked_before: liked
    before that day began (UTC). liked_after: liked on that day or later. A
    day is a date or "YYYY-MM-DD"; a datetime is taken as that exact instant
    (UTC when it has no time zone).
    ids: video ids. unavailable: True for deleted or private videos only,
    False for available ones only.
    """
    before = _day_start(liked_before) if liked_before is not None else None
    after = _day_start(liked_after) if liked_after is not None else None
    wanted_ids = set(ids) if ids is not None else None
    folded = channel.casefold() if channel is not None else None
    selected = []
    for video in videos:
        if folded is not None and folded not in (
            (video.get("channel_id") or "").casefold(),
            (video.get("channel_title") or "").casefold(),
        ):
            continue
        liked_at = datetime.fromisoformat(video["liked_at"]) if video.get("liked_at") else None
        if before is not None and (liked_at is None or liked_at >= before):
            continue
        if after is not None and (liked_at is None or liked_at < after):
            continue
        if wanted_ids is not None and video["video_id"] not in wanted_ids:
            continue
        if unavailable is not None and video["available"] == unavailable:
            continue
        selected.append(video)
    return selected


# Rating in bulk


class CannotRate(Exception):
    """A video this run cannot act on, for a reason known before any request."""


def _reason(error):
    try:
        return json.loads(error.content)["error"]["errors"][0]["reason"]
    except (ValueError, KeyError, IndexError, TypeError):
        return str(error.resp.status)


def _run(videos, act, *, apply, limit):
    """Apply act to each video, once, at most limit of them, unless a dry run.

    The run stops at the first quota error, leaving the rest in not_done;
    other errors are reported in failed and the run goes on. Acting twice on
    a video changes nothing, so a stopped run can be repeated.
    """
    unique = {}
    for video in videos:
        unique.setdefault(video["video_id"], video)
    ordered = list(unique.values())
    planned = [video["video_id"] for video in ordered[:limit]]
    result = {
        "planned": planned,
        "over_limit": [video["video_id"] for video in ordered[limit:]],
        "done": [],
        "not_done": [],
        "failed": {},
        "stopped": None,
        "cost": len(planned) * RATE_COST,
    }
    if not apply:
        return result
    for position, video in enumerate(ordered[:limit]):
        video_id = video["video_id"]
        try:
            act(video)
        except CannotRate as error:
            logger.info("Skipped %s: %s", video_id, error)
            result["failed"][video_id] = str(error)
            continue
        except HttpError as error:
            reason = _reason(error)
            if reason in ("quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded"):
                logger.info("Stopped at %s: %s", video_id, reason)
                result["stopped"] = reason
                result["not_done"] = planned[position:]
                break
            logger.info("Failed on %s: %s", video_id, reason)
            result["failed"][video_id] = reason
            continue
        result["done"].append(video_id)
    return result


def rate_videos(client, video_ids, rating, *, apply=False, limit=DEFAULT_LIMIT):
    """Rate videos by id "like" or "none"; a dry run unless apply is True."""
    if rating not in ("like", "none"):
        raise ValueError('rating must be "like" or "none"')

    def rate(video):
        client.youtube.videos().rate(id=video["video_id"], rating=rating).execute()
        logger.info("Rated %s %s", video["video_id"], rating)

    return _run([{"video_id": video_id} for video_id in video_ids], rate, apply=apply, limit=limit)


def unlike_videos(client, videos, *, apply=False, limit=DEFAULT_LIMIT):
    """Unlike liked-video records; a dry run unless apply is True.

    YouTube refuses to rate deleted or private videos, so those are removed
    from the likes playlist by their item_id instead (both cost 50 units).
    """

    def unlike(video):
        if video.get("available", True):
            client.youtube.videos().rate(id=video["video_id"], rating="none").execute()
            logger.info("Unliked %s", video["video_id"])
            return
        if not video.get("item_id"):
            raise CannotRate("unavailable, and the export has no item_id: export again")
        client.youtube.playlistItems().delete(id=video["item_id"]).execute()
        logger.info("Removed unavailable %s from the likes", video["video_id"])

    return _run(videos, unlike, apply=apply, limit=limit)


def like_videos(client, videos, *, apply=False, limit=DEFAULT_LIMIT):
    """Like liked-video records again, as an undo log holds them."""

    def like(video):
        if not video.get("available", True):
            raise CannotRate("deleted or private: YouTube does not let it be liked again")
        client.youtube.videos().rate(id=video["video_id"], rating="like").execute()
        logger.info("Liked %s again", video["video_id"])

    return _run(videos, like, apply=apply, limit=limit)
