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
    sample = [e for e in entries[:200] if isinstance(e, dict)]
    if not sample or not all("time" in e and "header" in e for e in sample):
        return False
    watched = sum("watch?v=" in (e.get("titleUrl") or "") for e in sample)
    searched = sum("search_query=" in (e.get("titleUrl") or "") for e in sample)
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


def history_record(entry):
    """One watched video, or None for an entry that is not a watch."""
    title = entry.get("title") or ""
    video_id = _video_id(entry.get("titleUrl"))
    subtitles = entry.get("subtitles") or [{}]
    # A removed video has no link at all, whatever the account's language;
    # a link that is not a video (a post, a story) is not a watch.
    removed = not entry.get("titleUrl")
    if video_id is None and not removed:
        return None
    return {
        "video_id": video_id,
        # Only the English prefix is known; other languages keep their text.
        "title": title[len(ENGLISH_PREFIX) :] if title.startswith(ENGLISH_PREFIX) and not removed else title,
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


def import_history(source, path, *, include_ads=False, include_music=False, now=None):
    """Read a Takeout export and write history.json, newest first.

    Returns the summary and what was left out, and never a title or URL.
    """
    records = [r for r in map(history_record, find_watch_history(source)) if r]
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
