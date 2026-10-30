"""Stable playlist artwork plans and offline generation from snapshots."""

import json
from pathlib import Path
import re

from . import artwork

SCHEMA = "youtube3.playlist-artwork.v1"
VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")


def playlist_snapshot(client, playlist_id):
    """Read a playlist and video availability; no account writes."""
    snippet = client.playlist_snippet(playlist_id)
    if snippet is None:
        raise artwork.ArtworkError("Playlist is missing or inaccessible")
    records = []
    for page in client.iterate_videos_in_playlist(playlist_id):
        items = page.get("items", [])
        ids = [item.get("contentDetails", {}).get("videoId") for item in items]
        details = client.video_details(list(dict.fromkeys(value for value in ids if value)))
        for item, video_id in zip(items, ids, strict=True):
            records.append({"video_id": video_id, "position": item["snippet"]["position"] + 1,
                            "title": item["snippet"].get("title", ""), "available": video_id in details})
    return {"playlist_id": playlist_id, "title": snippet.get("title", ""), "items": records}


def plan_playlist_artwork(snapshot, background, output_dir, *, start=1, end=None, number_offset=0,
                          cover_text=None, text="Episode {episode}", **render_options):
    """Create a fixed ID/position-to-file manifest. Ranges are 1-based and inclusive.

    Duplicate videos retain separate positions and images; unavailable entries
    retain their positions/numbering but have no output image. No files are written.
    """
    artwork._integer(start, "Start position", 1)
    if end is not None:
        artwork._integer(end, "End position", start)
    if isinstance(number_offset, bool) or not isinstance(number_offset, int):
        raise artwork.ArtworkError("Number offset must be an integer")
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("items"), list):
        raise artwork.ArtworkError("Snapshot must contain an items list")
    if not isinstance(snapshot.get("playlist_id"), str) or not snapshot["playlist_id"]:
        raise artwork.ArtworkError("Snapshot must identify a playlist")
    output_dir = Path(output_dir).expanduser().resolve()
    entries, positions = [], set()
    for item in snapshot["items"]:
        if not isinstance(item, dict):
            raise artwork.ArtworkError("Snapshot entries must be objects")
        position = artwork._integer(item.get("position"), "Playlist position", 1)
        if position in positions:
            raise artwork.ArtworkError(f"Duplicate playlist position: {position}")
        positions.add(position)
        if position < start or (end is not None and position > end):
            continue
        episode = artwork._integer(position + number_offset, "Episode")
        video_id = item.get("video_id")
        available = item.get("available", True)
        if not isinstance(available, bool):
            raise artwork.ArtworkError("Availability must be true or false")
        if available and (not isinstance(video_id, str) or not VIDEO_ID.fullmatch(video_id)):
            raise artwork.ArtworkError(f"Invalid video ID at position {position}")
        entry = {"video_id": video_id, "position": position, "episode": episode,
                 "title": item.get("title", ""), "state": "planned" if available else "unavailable", "render": None}
        if available:
            entry["render"] = artwork.plan_thumbnail(
                background, output_dir / f"{position:04d}-{video_id}.png", text=text, episode=episode,
                preset="video", **render_options)
        entries.append(entry)
    if not entries:
        raise artwork.ArtworkError("No entries in the selected playlist range")
    cover = artwork.plan_thumbnail(background, output_dir / "playlist-cover.png", preset="cover",
                                    text=cover_text if cover_text is not None else snapshot.get("title", ""),
                                    **render_options)
    return {"schema": SCHEMA, "playlist_id": snapshot["playlist_id"], "title": snapshot.get("title", ""),
            "entries": sorted(entries, key=lambda value: value["position"]),
            "cover": {"state": "planned", "render": cover}}


def validate_manifest(manifest):
    """Reject ambiguous/tampered manifest mappings before rendering or applying."""
    if not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA:
        raise artwork.ArtworkError("Unsupported artwork manifest schema")
    if not isinstance(manifest.get("playlist_id"), str) or not manifest["playlist_id"]:
        raise artwork.ArtworkError("Manifest must identify a playlist")
    if not isinstance(manifest.get("entries"), list) or not manifest["entries"]:
        raise artwork.ArtworkError("Manifest has no entries")
    positions, outputs = set(), set()
    for entry in manifest["entries"]:
        if not isinstance(entry, dict):
            raise artwork.ArtworkError("Manifest entries must be objects")
        position = artwork._integer(entry.get("position"), "Playlist position", 1)
        if position in positions:
            raise artwork.ArtworkError("Manifest has duplicate positions")
        positions.add(position)
        if entry.get("state") == "unavailable":
            if entry.get("render") is not None:
                raise artwork.ArtworkError("Unavailable entries must not have a rendering")
            continue
        if not isinstance(entry.get("video_id"), str) or not VIDEO_ID.fullmatch(entry["video_id"]):
            raise artwork.ArtworkError("Manifest has an invalid video ID")
        _output(entry.get("render"), outputs)
    if not isinstance(manifest.get("cover"), dict):
        raise artwork.ArtworkError("Manifest has no separate playlist cover")
    _output(manifest["cover"].get("render"), outputs)
    return manifest


def _output(plan, outputs):
    if not isinstance(plan, dict) or not isinstance(plan.get("output"), str):
        raise artwork.ArtworkError("Manifest entry has no output file")
    output = Path(plan["output"]).resolve()
    if output in outputs:
        raise artwork.ArtworkError("Manifest entries must use distinct output files")
    outputs.add(output)


def save_manifest(manifest, path, *, overwrite=False):
    validate_manifest(manifest)
    plans = [entry["render"] for entry in manifest["entries"] if entry.get("render")]
    plans.append(manifest["cover"]["render"])
    protected = {Path(plan[key]).resolve() for plan in plans for key in ("background", "output", "font") if plan.get(key)}
    if Path(path).resolve() in protected:
        raise artwork.ArtworkError("Manifest path must differ from image inputs and outputs")
    artwork.save_bytes(path, (json.dumps(manifest, indent=2) + "\n").encode("utf-8"), overwrite=overwrite)


def load_manifest(path):
    return validate_manifest(json.loads(Path(path).read_text(encoding="utf-8")))


def render_playlist_artwork(manifest, *, overwrite=False):
    """Render an immutable plan offline, without consulting the current playlist.

    Validate every path before rendering. A later rendering failure can leave
    earlier images; the manifest's fixed mapping remains valid for retry.
    """
    validate_manifest(manifest)
    plans = [entry["render"] for entry in manifest["entries"] if entry.get("render")]
    plans.append(manifest["cover"]["render"])
    checked = []
    for plan in plans:
        options = dict(plan)
        options["overwrite"] = overwrite
        checked.append(artwork.plan_thumbnail(options.pop("background"), options.pop("output"), **options))
    for plan in checked:
        artwork.render_plan(plan)
    return manifest
