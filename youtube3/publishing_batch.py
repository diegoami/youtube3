"""Fixed, reviewable publishing plans from explicit configuration entries."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re

from . import artwork, publishing_config as config, publishing_job as jobs

BATCH_SCHEMA = "youtube3.publishing-batch.v1"
PLAN_SCHEMA = "youtube3.publishing-plan.v1"
ENTRY_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")


def playlist_ids(values):
    if not isinstance(values, list) or any(not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value) for value in values):
        raise ValueError("playlists must be a list of playlist IDs")
    if len(values) != len(set(values)):
        raise ValueError("Duplicate playlist destination")
    return values


def resolve_batch(path, *, overrides=None):
    """Resolve local configuration only. Inputs, numbering and schedules stay fixed."""
    root = Path(path).expanduser().resolve().parent
    document = config.read_document(path)
    if set(document) - {"schema", "presets", "preset", "settings", "schedule", "entries", "playlists"} or document.get("schema") != BATCH_SCHEMA:
        raise ValueError("Unsupported batch configuration schema/fields")
    entries = document.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValueError("Batch must contain explicit entries")
    base = config.settings_layer(document.get("settings", {}), root)
    destinations = playlist_ids(document.get("playlists", []))
    cadence = document.get("schedule")
    start, minutes = None, None
    if cadence is not None:
        if not isinstance(cadence, dict) or set(cadence) != {"start", "interval_minutes"} or not isinstance(cadence["start"], str):
            raise ValueError("schedule needs an ISO start and interval_minutes")
        start = datetime.fromisoformat(cadence["start"])
        minutes = cadence["interval_minutes"]
        if start.tzinfo is None or start.utcoffset() is None:
            raise ValueError("Cadence start must include an explicit UTC offset")
        if isinstance(minutes, bool) or not isinstance(minutes, int) or minutes <= 0:
            raise ValueError("interval_minutes must be a positive integer")
        start = start.astimezone(timezone.utc)
    preset_path = config.local_path(document["presets"], root) if document.get("presets") else None
    seen_ids, seen_sources, resolved = set(), set(), []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or set(entry) - {"id", "config", "file", "video_id", "settings", "episode", "playlists"}:
            raise ValueError("Invalid batch entry fields")
        identity = entry.get("id")
        if not isinstance(identity, str) or not ENTRY_ID.fullmatch(identity) or identity in seen_ids:
            raise ValueError("Each entry needs a unique simple id")
        seen_ids.add(identity)
        if entry.get("file") is not None and entry.get("video_id") is not None:
            raise ValueError("Choose file or video_id per entry")
        video_config = config.local_path(entry["config"], root) if entry.get("config") else None
        video_document = config.read_document(video_config) if video_config else {}
        episode = entry.get("episode", video_document.get("episode", index + 1))
        defaults = dict(base)
        if start is not None:
            defaults.update(publish_at=(start + timedelta(minutes=index * minutes)).isoformat().replace("+00:00", "Z"), privacy=None)
        row = config.resolve_video_config(video_config,
            presets=None if video_document.get("presets") else preset_path,
            preset=None if video_document.get("preset") else document.get("preset"),
            defaults=defaults, episode=episode,
            file=config.local_path(entry["file"], root) if entry.get("file") else None, video_id=entry.get("video_id"),
            overrides=config.merge_layers(config.settings_layer(entry.get("settings", {}), root), overrides or {}))
        source = ("file", row["file"]) if row["file"] is not None else ("video", row["video_id"])
        if source in seen_sources:
            raise ValueError("A batch cannot target the same source twice")
        seen_sources.add(source)
        resolved.append({"id": identity, **row, "playlists": playlist_ids(entry.get("playlists", destinations))})
    return resolved


def plan_batch(client, entries):
    """Read/preflight every job and playlist without writing files or account data."""
    channel_id = client.signed_in_channel()["id"]
    result, checked_playlists = [], set()
    for entry in entries:
        settings = dict(entry["settings"])
        if settings.pop("profile", client.profile) != client.profile:
            raise ValueError("Batch entries must use the selected profile")
        config.check_destination(client, settings)
        settings.pop("expected_channel_id", None)
        job = jobs.plan_publishing_job(client, file=entry["file"], video_id=entry["video_id"], **settings)
        for playlist_id in entry["playlists"]:
            if playlist_id not in checked_playlists:
                snippet = client.playlist_snippet(playlist_id)
                if not snippet or snippet.get("channelId") != channel_id:
                    raise ValueError("Destination playlist is missing or belongs to another channel")
                checked_playlists.add(playlist_id)
        result.append({"id": entry["id"], "job": job, "playlists": entry["playlists"]})
    return validate_plan({"schema": PLAN_SCHEMA, "channel_id": channel_id, "profile": client.profile, "entries": result})


def validate_plan(plan):
    if not isinstance(plan, dict) or set(plan) != {"schema", "channel_id", "profile", "entries"} or plan.get("schema") != PLAN_SCHEMA:
        raise ValueError("Unsupported publishing batch plan")
    if not isinstance(plan["entries"], list) or not plan["entries"]:
        raise ValueError("Publishing batch plan is empty")
    seen = set()
    for entry in plan["entries"]:
        if not isinstance(entry, dict) or set(entry) != {"id", "job", "playlists"}:
            raise ValueError("Invalid batch plan entry")
        if not isinstance(entry["id"], str) or not ENTRY_ID.fullmatch(entry["id"]) or entry["id"] in seen:
            raise ValueError("Invalid/duplicate batch entry ID")
        seen.add(entry["id"])
        job = jobs.validate_job(entry["job"])
        if job["channel_id"] != plan["channel_id"] or job["profile"] != plan["profile"]:
            raise ValueError("Batch has mixed destination channels/profiles")
        playlist_ids(entry["playlists"])
    return plan


def save_plan(plan, path):
    validate_plan(plan)
    for entry in plan["entries"]:
        job = entry["job"]
        inputs = ([job["upload"]["file"]["path"]] if job["upload"] else []) + ([job["thumbnail"]["path"]] if job["thumbnail"] else [])
        if any(Path(path).resolve() == Path(source).resolve() for source in inputs):
            raise ValueError("Plan destination must differ from input media")
    artwork.save_bytes(path, (json.dumps(plan, indent=2) + "\n").encode("utf-8"))


def load_plan(path):
    return validate_plan(config.read_document(path))


def ensure_playlist_member(client, playlist_id, video_id, *, allow_insert=True):
    """Check first, add only if missing. Unknown prior writes may use read-only recovery."""
    snippet = client.playlist_snippet(playlist_id)
    if not snippet or snippet.get("channelId") != client.signed_in_channel()["id"]:
        raise ValueError("Playlist is missing or belongs to another channel")
    response = client.youtube.playlistItems().list(part="snippet", playlistId=playlist_id, videoId=video_id, maxResults=50).execute()
    if response.get("items"):
        return {"state": "present", "playlist_id": playlist_id, "video_id": video_id}
    if not allow_insert:
        return {"state": "unknown", "playlist_id": playlist_id, "video_id": video_id}
    client.youtube.playlistItems().insert(part="snippet", body={"snippet": {
        "playlistId": playlist_id, "resourceId": {"kind": "youtube#video", "videoId": video_id}}}).execute()
    return {"state": "added", "playlist_id": playlist_id, "video_id": video_id}
