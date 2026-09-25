"""The watch history, read-only, from a Google Takeout export.

The YouTube Data API has no access to watch history, so this reads the
watch-history.json that Takeout produces when asked for JSON. Takeout names
its files and folders in the account's language, so the file is found by
its contents, not its name. Nothing here logs a title or a URL.
"""

import json
import logging
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .likes import write_json_atomically

logger = logging.getLogger("youtube3")

ENGLISH_PREFIX = "Watched "
TOP_CHANNELS = 200


class HistoryError(Exception):
    pass


def _looks_like_watch_history(entries):
    """A Takeout activity list whose links are mostly videos, not searches."""
    if not isinstance(entries, list) or not entries:
        return False
    # The whole file, not a sample: its first entries may all be searches.
    activities = [e for e in entries if isinstance(e, dict)]
    if not activities or not all("time" in e and "header" in e for e in activities):
        return False
    watched = sum("watch?v=" in (e.get("titleUrl") or "") for e in activities)
    searched = sum("search_query=" in (e.get("titleUrl") or "") for e in activities)
    return watched > searched


def _candidates(source):
    """(name, bytes) of every .json and .html file in a Takeout zip or folder."""
    source = Path(source)
    if source.is_dir():
        for path in sorted(source.rglob("*")):
            if path.suffix.lower() in (".json", ".html") and path.is_file():
                yield str(path.relative_to(source)), path.read_bytes
    elif zipfile.is_zipfile(source):
        with zipfile.ZipFile(source) as archive:
            for name in sorted(archive.namelist()):
                if name.lower().endswith((".json", ".html")):
                    yield name, (lambda name=name: archive.read(name))
    else:
        raise HistoryError(f"{source} is neither a Takeout zip nor a folder")


def find_watch_history(source):
    """The entries of the watch history in a Takeout export (zip or folder)."""
    html_history = False
    for name, read in _candidates(source):
        if name.lower().endswith(".html"):
            # Names are in the account's language; the links are not.
            html_history = html_history or b"youtube.com/watch?v=" in read()
            continue
        try:
            entries = json.loads(read().decode("utf-8-sig"))
        except (ValueError, UnicodeDecodeError):
            continue
        if _looks_like_watch_history(entries):
            return entries
    if html_history:
        raise HistoryError(
            "the export has the history as HTML: export it again with History set to JSON "
            "(Takeout, All YouTube data included, Multiple formats)"
        )
    raise HistoryError("no watch history found in the export")


def _video_id(url):
    if not url:
        return None
    query = parse_qs(urlparse(url).query)
    return query.get("v", [None])[0]


def _channel_id(url):
    path = urlparse(url or "").path
    return path.split("/channel/", 1)[1].split("/")[0] if "/channel/" in path else None


# Takeout's placeholder for a video deleted or made private since: its own
# link wrapped in a fixed phrase, and no channel. In English the phrase is
# "Watched <link>"; the bare link is accepted too. An export in another
# language gives its phrase explicitly (import_history's placeholders): it is
# never guessed, because genuine titles can have the same shape (#59), and an
# entry in an unknown phrasing stays a watch.
KNOWN_PLACEHOLDERS = frozenset({"Watched {}", "{}"})


def _wrapping(entry):
    """The title with its own link replaced by {}, for an entry with no channel."""
    url, title = entry.get("titleUrl"), entry.get("title") or ""
    if not url or entry.get("subtitles") or url not in title:
        return None
    return title.replace(url, "{}")


def history_record(entry, placeholders=KNOWN_PLACEHOLDERS):
    """One watched video, or None for an entry that is not a watch.

    placeholders: the phrasings that mark an unavailable video, {} standing for its link.
    """
    title = entry.get("title") or ""
    video_id = _video_id(entry.get("titleUrl"))
    subtitles = entry.get("subtitles") or [{}]
    url = entry.get("titleUrl")
    # Unavailable: no link at all, or a placeholder phrasing around its own link.
    removed = not url or _wrapping(entry) in placeholders
    # A link that is not a video (a post, a story) is not a watch.
    if video_id is None and not removed:
        return None
    if url and removed:
        title = None  # the URL is not a title
    return {
        "video_id": video_id,
        # Only the English prefix is known; other languages keep their text.
        "title": title[len(ENGLISH_PREFIX) :] if title and title.startswith(ENGLISH_PREFIX) and not removed else title,
        "channel_id": _channel_id(subtitles[0].get("url")),
        "channel_title": subtitles[0].get("name"),
        "watched_at": entry.get("time"),
        "removed": removed,
        "ad": any(detail.get("name") == "From Google Ads" for detail in entry.get("details") or []),
        "music": entry.get("header") == "YouTube Music",
    }


def summarize(records):
    views = Counter(r["video_id"] for r in records if r["video_id"])
    channels = Counter((r["channel_id"], r["channel_title"]) for r in records if r["channel_id"])
    times = sorted(r["watched_at"] for r in records if r["watched_at"])
    return {
        "count": len(records),
        "videos": len(views),
        "rewatched": sum(1 for n in views.values() if n > 1),
        "removed": sum(r["removed"] for r in records),
        "first": times[0] if times else None,
        "last": times[-1] if times else None,
        "top_channels": [
            {"id": channel_id, "title": title, "count": count}
            for (channel_id, title), count in channels.most_common(TOP_CHANNELS)
        ],
    }


def import_history(source, path, *, include_ads=False, include_music=False, placeholders=KNOWN_PLACEHOLDERS, now=None):
    """Read a Takeout export and write history.json, newest first.

    Returns the summary and what was left out, and never a title or URL.
    """
    entries = find_watch_history(source)
    records = [r for r in (history_record(entry, placeholders) for entry in entries) if r]
    ads = sum(r["ad"] for r in records)
    music = sum(r["music"] for r in records)
    kept = [r for r in records if (include_ads or not r["ad"]) and (include_music or not r["music"])]
    kept.sort(key=lambda r: r["watched_at"] or "", reverse=True)
    summary = summarize(kept)
    now = now or datetime.now(timezone.utc)
    write_json_atomically(
        path,
        {"imported_at": now.isoformat(timespec="seconds"), "summary": summary, "videos": kept},
    )
    logger.info("Imported %d watches", len(kept))
    return {**summary, "left_out": {"ads": 0 if include_ads else ads, "music": 0 if include_music else music}}


# Selecting what to act on (youtube3.actions)


def watched_videos(videos):
    """Each watched video once, most recently watched first, with its views.

    Removed videos are left out: they have no id to act on.
    """
    seen = {}
    for record in sorted(videos, key=lambda r: r["watched_at"] or "", reverse=True):
        if not record["video_id"] or record["removed"]:
            continue  # nothing to act on: gone, or unavailable
        video = seen.get(record["video_id"])
        if video is None:
            seen[record["video_id"]] = {
                "video_id": record["video_id"],
                "title": record["title"],
                "channel_id": record["channel_id"],
                "channel_title": record["channel_title"],
                "last_watched": record["watched_at"],
                "first_watched": record["watched_at"],
                "views": 1,
            }
        else:
            video["views"] += 1
            video["first_watched"] = record["watched_at"]
    return list(seen.values())


def _day(value):
    """The start of a day (a date or YYYY-MM-DD) in UTC, as the ISO text history uses."""
    return datetime.fromisoformat(str(value)[:10]).replace(tzinfo=timezone.utc)


def _when(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00")) if iso else None


def select_watched(videos, *, channel=None, watched_after=None, watched_before=None, min_views=None, ids=None):
    """Watched videos matching every criterion given; no criterion matches all.

    channel: an id, or a title in any case. watched_after: last watched on
    that day or later (UTC). watched_before: last watched before that day
    began. min_views: watched at least that many times. ids: video ids.
    """
    after = _day(watched_after) if watched_after else None
    before = _day(watched_before) if watched_before else None
    folded = channel.casefold() if channel else None
    wanted = set(ids) if ids is not None else None
    selected = []
    for video in watched_videos(videos):
        last = _when(video["last_watched"])
        if folded and folded not in ((video["channel_id"] or "").casefold(), (video["channel_title"] or "").casefold()):
            continue
        if after and (last is None or last < after):
            continue
        if before and (last is None or last >= before):
            continue
        if min_views and video["views"] < min_views:
            continue
        if wanted is not None and video["video_id"] not in wanted:
            continue
        selected.append(video)
    return selected


def top_channels(videos, *, min_views=1):
    """Channels by how many watches they have, most first, then by title."""
    counts = {}
    for record in videos:
        if not record["channel_id"]:
            continue
        entry = counts.setdefault(
            record["channel_id"], {"channel_id": record["channel_id"], "channel_title": record["channel_title"], "views": 0}
        )
        entry["views"] += 1
    ranked = sorted(counts.values(), key=lambda c: (-c["views"], (c["channel_title"] or "").casefold()))
    return [channel for channel in ranked if channel["views"] >= min_views]


# Finding the export, and checking whose it is


def download_folders():
    """Where a browser saves Takeout: ~/Downloads, and on WSL the Windows ones too."""
    folders = [Path.home() / "Downloads"]
    windows_users = Path("/mnt/c/Users")
    if windows_users.is_dir():
        folders += sorted(windows_users.glob("*/Downloads"))
    return folders


def find_latest_takeout(folders=None):
    """The newest takeout-*.zip holding a watch history, or None."""
    candidates = []
    for folder in folders if folders is not None else download_folders():
        try:
            candidates += [path for path in Path(folder).glob("takeout-*.zip") if path.is_file()]
        except OSError:
            continue  # a folder we may not read
    for path in sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            find_watch_history(path)
        except (HistoryError, OSError, zipfile.BadZipFile):
            continue
        return path
    return None


# Few of a channel's likes among its watches means the export is another account's.
MIN_LIKES_TO_JUDGE = 50
MIN_SHARE_OF_LIKES_WATCHED = 0.2


def likes_overlap(records, liked_ids):
    """How many of a channel's likes appear among the watches, and whether that is suspicious."""
    watched = {record["video_id"] for record in records if record["video_id"]}
    liked = set(liked_ids)
    found = len(liked & watched)
    share = found / len(liked) if liked else None
    return {
        "liked": len(liked),
        "found": found,
        "share": share,
        "another_account": len(liked) >= MIN_LIKES_TO_JUDGE and share < MIN_SHARE_OF_LIKES_WATCHED,
    }
