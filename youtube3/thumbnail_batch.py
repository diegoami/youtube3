"""Preview/apply video thumbnails from an explicit playlist artwork manifest."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path

from googleapiclient.errors import HttpError

from . import artwork, playlist_artwork, publish

SCHEMA = "youtube3.thumbnail-batch.v1"


class ThumbnailBatchError(ValueError):
    def __init__(self, message, report=None):
        super().__init__(message)
        self.report = report


def checked_image(path, *, square=False, max_bytes=publish.MAX_THUMBNAIL_BYTES):
    """Decode the whole PNG/JPEG before uploads, returning a content fingerprint."""
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise ThumbnailBatchError(f"Image is not a file: {path}")
    if path.stat().st_size > max_bytes:
        raise ThumbnailBatchError(f"Image exceeds the library policy of {max_bytes} bytes: {path}")
    Image, *_ = artwork._pillow()
    try:
        with Image.open(path) as image:
            if image.format not in ("PNG", "JPEG"):
                raise ThumbnailBatchError("Image must be PNG or JPEG")
            image.verify()
        with Image.open(path) as image:
            image.load()
            width, height = image.size
        if square and width != height:
            raise ThumbnailBatchError("Playlist cover must be square (1:1)")
        if not square and width < publish.MIN_THUMBNAIL_WIDTH:
            raise ThumbnailBatchError(f"Video thumbnail must be at least {publish.MIN_THUMBNAIL_WIDTH} pixels wide")
    except (OSError, ValueError) as error:
        raise ThumbnailBatchError(f"Invalid image: {error}") from None
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "bytes": path.stat().st_size, "width": width, "height": height}


def plan_thumbnail_batch(client, manifest):
    """Validate all mappings, decoded images, ownership and eligibility before any write."""
    playlist_artwork.validate_manifest(manifest)
    entries, ids = [], set()
    for entry in manifest["entries"]:
        if entry["state"] == "unavailable":
            continue
        video_id = entry["video_id"]
        if video_id in ids:
            raise ThumbnailBatchError(f"Duplicate video ID {video_id}: select one explicit image per video")
        ids.add(video_id)
        entries.append({"video_id": video_id, "position": entry["position"],
                        "image": checked_image(entry["render"]["output"]), "state": "pending"})
    if not entries:
        raise ThumbnailBatchError("No available video thumbnails in the manifest")
    channel = client.signed_in_channel()
    channels = client.youtube.channels().list(part="status", mine=True).execute().get("items", [])
    if not channels or channels[0].get("status", {}).get("longUploadsStatus") != "allowed":
        raise ThumbnailBatchError("Custom thumbnails need a verified eligible channel: https://www.youtube.com/verify")
    ordered = [entry["video_id"] for entry in entries]
    for start in range(0, len(ordered), 50):
        details = client.video_details(ordered[start:start + 50])
        for video_id in ordered[start:start + 50]:
            if details.get(video_id, {}).get("snippet", {}).get("channelId") != channel["id"]:
                raise ThumbnailBatchError(f"Video {video_id} is missing or belongs to another channel")
    return {"schema": SCHEMA, "playlist_id": manifest["playlist_id"], "channel_id": channel["id"],
            "entries": entries, "cost": len(entries) * publish.THUMBNAIL_COST}


def _retry_plan(plan, previous):
    if previous is None:
        return plan
    if not isinstance(previous, dict):
        raise ThumbnailBatchError("Invalid thumbnail report")
    for key in ("schema", "playlist_id", "channel_id"):
        if previous.get(key) != plan[key]:
            raise ThumbnailBatchError("Retry report does not match this manifest/channel")
    previous_entries = previous.get("entries")
    if not isinstance(previous_entries, list) or len(previous_entries) != len(plan["entries"]):
        raise ThumbnailBatchError("Retry report has different mappings")
    for current, old in zip(plan["entries"], previous_entries, strict=True):
        if not isinstance(old, dict) or any(old.get(key) != current[key] for key in ("video_id", "position", "image")):
            raise ThumbnailBatchError("Retry report image/mapping changed; inspect it and create a new explicit plan")
        if old.get("state") not in ("pending", "failed", "successful"):
            raise ThumbnailBatchError("Invalid thumbnail result state")
        if old["state"] == "successful":
            current["state"] = "successful"
    return plan


def _save_report(report, path, *, overwrite):
    # Reports are an explicit allowlist; no raw API exception or credentials.
    try:
        artwork.save_bytes(path, (json.dumps(report, indent=2) + "\n").encode("utf-8"), overwrite=overwrite)
    except OSError:
        raise ThumbnailBatchError("Checkpoint could not be saved; inspect returned report", deepcopy(report)) from None


def apply_thumbnail_batch(client, manifest, *, previous=None, report_path=None):
    """Apply only pending/failed entries; stop on first failure and checkpoint every result.

    Successes are never retried from a matching report. Revalidate the complete
    batch before the first write. The cover is intentionally not a video target.
    """
    report = _retry_plan(plan_thumbnail_batch(client, manifest), previous)
    if report_path:
        render_plans = [entry["render"] for entry in manifest["entries"] if entry.get("render")]
        render_plans.append(manifest["cover"]["render"])
        protected = {Path(plan[key]).resolve() for plan in render_plans
                     for key in ("background", "output", "font") if plan.get(key)}
        if Path(report_path).resolve() in protected:
            raise ThumbnailBatchError("Report path must differ from image files")
        _save_report(report, report_path, overwrite=previous is not None)
    for entry in report["entries"]:
        if entry["state"] == "successful":
            continue
        # Refuse file changes between preflight and each upload.
        if checked_image(entry["image"]["path"]) != entry["image"]:
            raise ThumbnailBatchError("Image changed after validation; no upload attempted for it", deepcopy(report))
        try:
            client.upload_thumbnail(entry["video_id"], entry["image"]["path"])
        except Exception as error:
            entry["state"] = "failed"
            entry["error"] = f"HTTP {error.resp.status}" if isinstance(error, HttpError) else "Thumbnail upload failed"
            if report_path:
                _save_report(report, report_path, overwrite=True)
            raise ThumbnailBatchError(f"Thumbnail application stopped at {entry['video_id']}", deepcopy(report)) from None
        entry["state"] = "successful"
        if report_path:
            try:
                _save_report(report, report_path, overwrite=True)
            except OSError:
                raise ThumbnailBatchError("Thumbnail applied but checkpoint failed; inspect returned report", deepcopy(report)) from None
    return report
