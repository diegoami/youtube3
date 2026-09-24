"""Publishing a video uploaded in Studio: thumbnail, metadata, and when it goes public."""

import logging
import os
import struct
from datetime import datetime, timezone

from googleapiclient.http import MediaFileUpload

logger = logging.getLogger("youtube3")

# The fields of each part the API lets an owner write. videos.update resets
# every mutable field of a part it is sent without, so a part is always sent
# whole: the current values, with the changes applied.
WRITABLE_SNIPPET = ("title", "description", "tags", "categoryId", "defaultLanguage", "defaultAudioLanguage")
WRITABLE_STATUS = (
    "privacyStatus",
    "publishAt",
    "embeddable",
    "license",
    "publicStatsViewable",
    "selfDeclaredMadeForKids",
    "containsSyntheticMedia",
)
PRIVACY = ("private", "unlisted", "public")

MAX_THUMBNAIL_BYTES = 2 * 1024 * 1024
MIN_THUMBNAIL_WIDTH = 640
MAX_TITLE = 100
MAX_DESCRIPTION_BYTES = 5000
MAX_TAGS = 500
UPDATE_COST = 50
THUMBNAIL_COST = 50


class PublishError(Exception):
    pass


def writable(part, fields):
    return {field: part[field] for field in fields if field in part}


# Thumbnails


# Start-of-frame markers, which carry the size (C4, C8 and CC are not frames).
JPEG_FRAMES = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}


def _jpeg_size(image):
    """(width, height) from the first frame header after the start marker."""
    image.seek(2)
    while True:
        byte = image.read(1)
        if not byte:
            return None, None
        if byte != b"\xff":
            continue
        marker = image.read(1)
        while marker == b"\xff":  # fill bytes
            marker = image.read(1)
        if not marker or marker[0] in (0xD9, 0xDA):  # end of image, or scan data before any frame
            return None, None
        if marker[0] == 0x01 or 0xD0 <= marker[0] <= 0xD7:  # no length follows
            continue
        length_bytes = image.read(2)
        if len(length_bytes) < 2:
            return None, None
        (length,) = struct.unpack(">H", length_bytes)
        if marker[0] in JPEG_FRAMES:
            frame = image.read(5)
            if len(frame) < 5:
                return None, None
            height, width = struct.unpack(">HH", frame[1:5])
            return width, height
        image.seek(length - 2, os.SEEK_CUR)


def image_type_and_size(path):
    """(media type, width, height) from a PNG or JPEG header, or (None, None, None)."""
    with open(path, "rb") as image:
        head = image.read(24)
        if head[:8] == b"\x89PNG\r\n\x1a\n" and head[12:16] == b"IHDR":
            if len(head) < 24:  # cut inside the header
                return "image/png", None, None
            width, height = struct.unpack(">II", head[16:24])
            return "image/png", width, height
        if head[:3] == b"\xff\xd8\xff":
            return ("image/jpeg", *_jpeg_size(image))
    return None, None, None


def check_thumbnail(path):
    """What YouTube will think of this file as a custom thumbnail."""
    report = {"path": str(path), "errors": [], "warnings": [], "type": None, "width": None, "height": None}
    if not os.path.isfile(path):
        report["errors"].append("no such file")
        return report
    report["bytes"] = os.path.getsize(path)
    if report["bytes"] > MAX_THUMBNAIL_BYTES:
        report["errors"].append(f"{report['bytes']} bytes: YouTube takes at most 2 MB")
    kind, width, height = image_type_and_size(path)
    report.update(type=kind, width=width, height=height)
    if kind is None:
        report["errors"].append("not a PNG or JPEG image")
    elif width is None:
        report["errors"].append("the image size could not be read")
    else:
        if width < MIN_THUMBNAIL_WIDTH:
            report["errors"].append(f"{width} px wide: YouTube needs at least {MIN_THUMBNAIL_WIDTH}")
        if width * 9 != height * 16:
            report["warnings"].append(f"{width}×{height} is not 16:9; YouTube will crop or pad it")
        if width < 1280 or height < 720:
            report["warnings"].append(f"{width}×{height} is below the recommended 1280×720")
    return report


def thumbnail_upload(path):
    kind, _, _ = image_type_and_size(path)
    return MediaFileUpload(str(path), mimetype=kind or "application/octet-stream")


# Planning and applying


def _when(publish_at):
    if isinstance(publish_at, str):
        publish_at = datetime.fromisoformat(publish_at)
    if publish_at.tzinfo is None:
        publish_at = publish_at.astimezone()  # local time
    return publish_at.astimezone(timezone.utc).replace(microsecond=0)


def plan_publish(
    client,
    video_id,
    *,
    title=None,
    description=None,
    tags=None,
    thumbnail=None,
    privacy=None,
    publish_at=None,
    now=None,
):
    """Read the video and work out what would change; nothing is written."""
    items = client.youtube.videos().list(id=video_id, part="snippet,status").execute().get("items")
    if not items:
        raise PublishError(f"{video_id}: no such video, or not one of yours")
    snippet = writable(items[0]["snippet"], WRITABLE_SNIPPET)
    status = writable(items[0]["status"], WRITABLE_STATUS)
    new_snippet, new_status = dict(snippet), dict(status)
    errors = []

    if title is not None:
        if not 1 <= len(title) <= MAX_TITLE:
            errors.append(f"the title needs 1 to {MAX_TITLE} characters, not {len(title)}")
        if "<" in title or ">" in title:
            errors.append("YouTube does not allow < or > in a title")
        new_snippet["title"] = title
    if description is not None:
        if len(description.encode("utf-8")) > MAX_DESCRIPTION_BYTES:
            errors.append(f"the description is over {MAX_DESCRIPTION_BYTES} bytes")
        if "<" in description or ">" in description:
            errors.append("YouTube does not allow < or > in a description")
        new_snippet["description"] = description
    if tags is not None:
        tags = [tag.strip() for tag in tags if tag.strip()]
        if sum(len(tag) for tag in tags) > MAX_TAGS:
            errors.append(f"the tags are over {MAX_TAGS} characters in total")
        new_snippet["tags"] = tags

    if privacy is not None:
        if privacy not in PRIVACY:
            errors.append(f"privacy must be one of {', '.join(PRIVACY)}")
        new_status["privacyStatus"] = privacy
        if privacy != "private":
            new_status.pop("publishAt", None)  # made visible now, not later
    if publish_at is not None:
        when = _when(publish_at)
        now = now or datetime.now(timezone.utc)
        if when <= now:
            errors.append(f"the scheduled time {when.isoformat()} is not in the future")
        if privacy not in (None, "private"):
            errors.append("a scheduled video stays private until its time; drop the privacy option")
        elif status.get("privacyStatus") == "public":
            errors.append("the video is already public, so it cannot be scheduled")
        new_status["privacyStatus"] = "private"
        new_status["publishAt"] = when.isoformat().replace("+00:00", "Z")

    changes = {}
    for field in WRITABLE_SNIPPET:
        if new_snippet.get(field) != snippet.get(field):
            changes[field] = (snippet.get(field), new_snippet.get(field))
    for field in WRITABLE_STATUS:
        if new_status.get(field) != status.get(field):
            changes[field] = (status.get(field), new_status.get(field))
    snippet_changes = any(field in changes for field in WRITABLE_SNIPPET)
    status_changes = any(field in changes for field in WRITABLE_STATUS)

    report = check_thumbnail(thumbnail) if thumbnail is not None else None
    if report:
        errors.extend(f"thumbnail: {error}" for error in report["errors"])
    return {
        "video_id": video_id,
        "title": snippet.get("title"),
        "changes": changes,
        "snippet": new_snippet if snippet_changes else None,
        "status": new_status if status_changes else None,
        "thumbnail": report,
        "errors": errors,
        "cost": (UPDATE_COST if snippet_changes or status_changes else 0) + (THUMBNAIL_COST if report else 0),
    }


def apply_publish(client, plan):
    """Send the plan's changes: one videos.update with whole parts, then the thumbnail."""
    if plan["errors"]:
        raise PublishError("; ".join(plan["errors"]))
    done = []
    parts = [part for part in ("snippet", "status") if plan[part] is not None]
    if parts:
        body = {"id": plan["video_id"], **{part: plan[part] for part in parts}}
        client.youtube.videos().update(part=",".join(parts), body=body).execute()
        logger.info("Updated %s of %s", " and ".join(parts), plan["video_id"])
        done.extend(parts)
    if plan["thumbnail"] is not None:
        client.youtube.thumbnails().set(
            videoId=plan["video_id"], media_body=thumbnail_upload(plan["thumbnail"]["path"])
        ).execute()
        logger.info("Set the thumbnail of %s", plan["video_id"])
        done.append("thumbnail")
    return done
