"""Acting on the watch history through the API: like, add to a playlist, subscribe.

The API cannot change the history itself, but it can act on what is in it.
Every action is a dry run unless applied, rates or inserts at most `limit`
items, stops at the quota, skips what is already done, and returns what it
created so the run can be undone (undo_actions).
"""

import json
import logging
import math
from datetime import datetime, timezone
from pathlib import Path

from googleapiclient.errors import HttpError

from .likes import DEFAULT_LIMIT, _reason, _run, write_json_atomically

logger = logging.getLogger("youtube3")

PLAYLIST_PRIVACY = ("private", "unlisted", "public")


def _pages(count):
    """Quota units to list count items, 50 to a page (1 unit each)."""
    return max(math.ceil(count / 50), 1)


def _skipping(items, skip, key, why):
    """(items to act on, {id: reason} of those skipped)."""
    kept = [item for item in items if item[key] not in skip]
    return kept, {item[key]: why for item in items if item[key] in skip}


def like_watched(client, videos, *, apply=False, limit=DEFAULT_LIMIT):
    """Like watched videos, skipping those already liked.

    The current likes are read from YouTube first (1 unit per 50), never from
    an export that may be stale: a video liked before the run must not be
    recorded as liked by it, or undo would remove the older like.
    """
    liked_ids = {video["video_id"] for video in client.iterate_liked_videos()}
    kept, skipped = _skipping(videos, liked_ids, "video_id", "already liked")

    def like(video):
        client.youtube.videos().rate(id=video["video_id"], rating="like").execute()
        logger.info("Liked %s", video["video_id"])

    result = _run(kept, like, apply=apply, limit=limit)
    result.update(skipped=skipped, created={}, read_cost=_pages(len(liked_ids)))
    return result


def playlist_video_ids(client, playlist_id):
    return {
        item["contentDetails"]["videoId"]
        for page in client.iterate_videos_in_playlist(playlist_id)
        for item in page["items"]
    }


def create_playlist(client, title, privacy="private"):
    if privacy not in PLAYLIST_PRIVACY:
        raise ValueError(f"privacy must be one of {', '.join(PLAYLIST_PRIVACY)}")
    body = {"snippet": {"title": title}, "status": {"privacyStatus": privacy}}
    playlist = client.youtube.playlists().insert(part="snippet,status", body=body).execute()
    logger.info("Created playlist %s", playlist["id"])
    return playlist["id"]


def add_to_playlist(client, videos, *, playlist_id=None, new_title=None, privacy="private", apply=False, limit=DEFAULT_LIMIT):
    """Add videos to a playlist, or to a new one titled new_title (created only when applied).

    Videos already in an existing playlist are skipped; created maps each
    video id to the playlist item made for it.
    """
    if (playlist_id is None) == (new_title is None):
        raise ValueError("give a playlist_id or a new_title, not both")
    existing = playlist_video_ids(client, playlist_id) if playlist_id else set()
    kept, skipped = _skipping(videos, existing, "video_id", "already in the playlist")
    created = {}
    target = {"id": playlist_id}

    def insert(video):
        if target["id"] is None:
            target["id"] = create_playlist(client, new_title, privacy)
        body = {
            "snippet": {
                "playlistId": target["id"],
                "resourceId": {"kind": "youtube#video", "videoId": video["video_id"]},
            }
        }
        item = client.youtube.playlistItems().insert(part="snippet", body=body).execute()
        created[video["video_id"]] = item["id"]
        logger.info("Added %s to %s", video["video_id"], target["id"])

    result = _run(kept, insert, apply=apply, limit=limit)
    # A new playlist costs one more insert, when there is anything to add.
    result["cost"] += 50 if new_title and result["planned"] else 0
    result.update(
        skipped=skipped,
        created=created,
        playlist_id=target["id"],
        new_playlist=bool(new_title and target["id"]),
        read_cost=_pages(len(existing)) if playlist_id else 0,
    )
    return result


def subscribed_channel_ids(client):
    return {subscription["id"] for subscription in client.iterate_subscriptions_in_channel()}


def subscribe_to(client, channels, *, apply=False, limit=DEFAULT_LIMIT):
    """Subscribe to channels, skipping those already subscribed.

    YouTube's own "subscriptionDuplicate" also counts as skipped. created maps
    each channel id to the subscription made for it.
    """
    subscribed = subscribed_channel_ids(client)
    kept, skipped = _skipping(channels, subscribed, "channel_id", "already subscribed")
    created = {}

    def subscribe(channel):
        body = {"snippet": {"resourceId": {"kind": "youtube#channel", "channelId": channel["channel_id"]}}}
        try:
            subscription = client.youtube.subscriptions().insert(part="snippet", body=body).execute()
        except HttpError as error:
            if _reason(error) == "subscriptionDuplicate":
                skipped[channel["channel_id"]] = "already subscribed"
                return
            raise
        created[channel["channel_id"]] = subscription["id"]
        logger.info("Subscribed to %s", channel["channel_id"])

    result = _run(kept, subscribe, apply=apply, limit=limit, key="channel_id")
    # A duplicate is not a success: it did nothing.
    result["done"] = [channel_id for channel_id in result["done"] if channel_id in created]
    result.update(skipped=skipped, created=created, read_cost=_pages(len(subscribed)))
    return result


# The log of an applied run, and its undo


def write_action_log(folder, action, items, result, now=None):
    """Save what a run created, as history-<action>-<time>.json, for undo_actions."""
    now = now or datetime.now(timezone.utc)
    key = "channel_id" if action == "subscribe" else "video_id"
    done = [dict(item, created=result["created"].get(item[key])) for item in items if item[key] in result["done"]]
    stem = f"history-{action}-{now.strftime('%Y%m%d-%H%M%S')}"
    path, counter = Path(folder) / f"{stem}.json", 2
    while path.exists():
        path, counter = Path(folder) / f"{stem}-{counter}.json", counter + 1
    log = {"action": action, "acted_at": now.isoformat(timespec="seconds"), "done": done}
    if action == "playlist":
        log.update(playlist_id=result["playlist_id"], new_playlist=result["new_playlist"])
    write_json_atomically(path, log)
    return path


def load_log(path):
    with open(path, encoding="utf-8") as log:
        return json.load(log)


def _already_gone(call):
    """Run a delete; one that finds nothing (404) was undone before, by a stopped run."""
    try:
        call()
    except HttpError as error:
        if error.resp.status != 404:
            raise


def undo_actions(client, log, *, apply=False, limit=None):
    """Reverse an applied run from its log; a dry run unless apply is True.

    like: rate the videos "none". playlist: delete the playlist the run
    created, or else the items it added. subscribe: delete the subscriptions.
    The whole log is undone unless a limit is given, and an undo stopped at
    the quota can be run again: what is already gone counts as undone.
    """
    action = log["action"]
    if limit is None:
        limit = max(len(log.get("done", [])), 1)
    if action == "playlist" and log.get("new_playlist"):
        playlist = [{"playlist_id": log["playlist_id"]}]

        def delete_playlist(item):
            _already_gone(client.youtube.playlists().delete(id=item["playlist_id"]).execute)
            logger.info("Deleted playlist %s", item["playlist_id"])

        return _run(playlist, delete_playlist, apply=apply, limit=limit, key="playlist_id")
    if action == "like":

        def unlike(item):
            try:
                client.youtube.videos().rate(id=item["video_id"], rating="none").execute()
            except HttpError as error:
                # A video deleted since the run keeps no like to remove.
                if _reason(error) != "videoNotFound":
                    raise

        return _run(log["done"], unlike, apply=apply, limit=limit)
    if action == "playlist":

        def remove(item):
            _already_gone(client.youtube.playlistItems().delete(id=item["created"]).execute)

        return _run(log["done"], remove, apply=apply, limit=limit)
    if action == "subscribe":

        def unsubscribe(item):
            _already_gone(client.youtube.subscriptions().delete(id=item["created"]).execute)

        return _run(log["done"], unsubscribe, apply=apply, limit=limit, key="channel_id")
    raise ValueError(f"not a log of an action run: {action!r}")


def mark_undone(path, result):
    """Move what an applied undo reversed from the log's done to its undone.

    So the same undo, run again (with --limit, or after a stop), carries on
    with what is left instead of starting over.
    """
    log = load_log(path)
    if log["action"] == "playlist" and log.get("new_playlist"):
        if log["playlist_id"] in result["done"]:
            log["undone"] = log.get("undone", []) + log["done"]
            log["done"], log["playlist_deleted"] = [], True
    else:
        key = "channel_id" if log["action"] == "subscribe" else "video_id"
        undone = set(result["done"])
        log["undone"] = log.get("undone", []) + [item for item in log["done"] if item[key] in undone]
        log["done"] = [item for item in log["done"] if item[key] not in undone]
    write_json_atomically(path, log)
