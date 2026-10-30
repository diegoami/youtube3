"""Single-file resumable uploads; preview by default and never restart an uncertain upload."""

from copy import deepcopy
from pathlib import Path
import time

import httplib2
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from . import publish, publishing_metadata

CHUNK_UNIT = 256 * 1024
DEFAULT_CHUNK_SIZE = 8 * 1024 * 1024
MAX_VIDEO_BYTES = 256 * 1024**3
VIDEO_TYPES = {".mp4": "video/mp4", ".m4v": "video/mp4", ".mov": "video/quicktime",
               ".webm": "video/webm", ".mkv": "video/x-matroska", ".avi": "video/x-msvideo",
               ".mpeg": "video/mpeg", ".mpg": "video/mpeg", ".flv": "video/x-flv"}


class UploadError(ValueError):
    """A safe upload failure. Unknown outcomes require manual recovery, never reupload."""

    def __init__(self, message, *, outcome="unknown", video_id=None):
        super().__init__(message)
        self.outcome = outcome
        self.video_id = video_id


def upload_spec(file, *, title, description="", category_id="22", tags=None, privacy="private",
                made_for_kids=None, notify_subscribers=False, retries=3, chunk_size=DEFAULT_CHUNK_SIZE,
                default_language=None, default_audio_language=None, license=None, embeddable=None,
                public_stats_viewable=None, contains_synthetic_media=None):
    """Validate local input and metadata without login, upload construction or account calls."""
    path = Path(file).expanduser().resolve()
    if not path.is_file():
        raise UploadError(f"Video is not a file: {path}", outcome="not_started")
    stat = path.stat()
    if not 0 < stat.st_size <= MAX_VIDEO_BYTES:
        raise UploadError("Video must be non-empty and at most 256 GiB", outcome="not_started")
    if path.suffix.lower() not in VIDEO_TYPES:
        raise UploadError(f"Unsupported video extension; use one of {', '.join(VIDEO_TYPES)}", outcome="not_started")
    if not isinstance(title, str) or not 1 <= len(title) <= publish.MAX_TITLE or "<" in title or ">" in title:
        raise UploadError("Title needs 1–100 characters without < or >", outcome="not_started")
    if (not isinstance(description, str) or len(description.encode("utf-8")) > publish.MAX_DESCRIPTION_BYTES
            or "<" in description or ">" in description):
        raise UploadError("Description must be <=5000 UTF-8 bytes without < or >", outcome="not_started")
    if not isinstance(category_id, str) or not category_id.isascii() or not category_id.isdigit():
        raise UploadError("Category ID must be a numeric string", outcome="not_started")
    if privacy not in publish.PRIVACY:
        raise UploadError("Privacy must be private, unlisted or public", outcome="not_started")
    if not isinstance(notify_subscribers, bool) or (made_for_kids is not None and not isinstance(made_for_kids, bool)):
        raise UploadError("Notification and made-for-kids values must be boolean", outcome="not_started")
    if isinstance(retries, bool) or not isinstance(retries, int) or not 0 <= retries <= 10:
        raise UploadError("Retries must be an integer from 0 to 10", outcome="not_started")
    if isinstance(chunk_size, bool) or not isinstance(chunk_size, int) or chunk_size < CHUNK_UNIT or chunk_size % CHUNK_UNIT:
        raise UploadError("Chunk size must be a positive multiple of 256 KiB", outcome="not_started")
    snippet = {"title": title, "description": description, "categoryId": category_id}
    if tags is not None:
        if not isinstance(tags, (list, tuple)) or any(not isinstance(tag, str) or not tag.strip() for tag in tags):
            raise UploadError("Tags must be a list of non-empty strings", outcome="not_started")
        tags = [tag.strip() for tag in tags]
        cost = sum(len(tag) + (2 if " " in tag else 0) for tag in tags) + max(0, len(tags) - 1)
        if cost > publish.MAX_TAGS:
            raise UploadError("Tags exceed the 500-character budget including separators/quotes", outcome="not_started")
        if tags:
            snippet["tags"] = tags
    status = {"privacyStatus": privacy}
    if made_for_kids is not None:
        status["selfDeclaredMadeForKids"] = made_for_kids
    try:
        extra_snippet, extra_status = publishing_metadata.parts(dict(default_language=default_language,
            default_audio_language=default_audio_language, license=license, embeddable=embeddable,
            public_stats_viewable=public_stats_viewable, contains_synthetic_media=contains_synthetic_media))
    except ValueError as error:
        raise UploadError(str(error), outcome="not_started") from None
    snippet.update(extra_snippet)
    status.update(extra_status)
    return {"file": {"path": str(path), "bytes": stat.st_size, "modified_ns": stat.st_mtime_ns,
                     "type": VIDEO_TYPES[path.suffix.lower()]}, "body": {"snippet": snippet, "status": status},
            "notify_subscribers": notify_subscribers, "retries": retries, "chunk_size": chunk_size,
            "quota": {"bucket": "Video Uploads", "units": 1}}


def plan_video_upload(client, file, **options):
    """No-upload preview with an explicit destination channel/profile and privacy."""
    plan = upload_spec(file, **options)
    channel = client.signed_in_channel()
    return {**plan, "channel_id": channel["id"], "profile": client.profile}


def _validate_plan(client, plan):
    body = plan["body"]
    snippet, status = body["snippet"], body["status"]
    extras = {key: snippet[value] for key, value in publishing_metadata.SNIPPET_FIELDS.items()
              if key != "category_id" and value in snippet}
    extras.update({key: status[value] for key, value in publishing_metadata.STATUS_FIELDS.items()
                   if key != "made_for_kids" and value in status})
    expected = plan_video_upload(client, plan["file"]["path"], title=snippet["title"],
        description=snippet.get("description", ""), category_id=snippet.get("categoryId", "22"),
        tags=snippet.get("tags"), privacy=status["privacyStatus"], made_for_kids=status.get("selfDeclaredMadeForKids"),
        notify_subscribers=plan["notify_subscribers"], retries=plan["retries"], chunk_size=plan["chunk_size"], **extras)
    if expected != plan:
        raise UploadError("File, upload settings or destination changed after planning", outcome="not_started")


def apply_video_upload(client, plan, *, progress=None):
    """Run one videos.insert and retry only within its known resumable session.

    Progress receives byte counts only. Never persist/return session URLs or raw
    API errors. There is intentionally no cross-process session resume here.
    """
    _validate_plan(client, plan)
    media = MediaFileUpload(plan["file"]["path"], mimetype=plan["file"]["type"],
                            chunksize=plan["chunk_size"], resumable=True)
    result = None
    try:
        request = client.youtube.videos().insert(part="snippet,status", body=deepcopy(plan["body"]),
                                                 notifySubscribers=plan["notify_subscribers"], media_body=media)
        failures, stalls, last_bytes = 0, 0, -1
        while True:
            try:
                status, response = request.next_chunk(num_retries=0)
            except (HttpError, OSError, httplib2.HttpLib2Error) as error:
                retryable = not isinstance(error, HttpError) or error.resp.status in (429, 500, 502, 503, 504)
                # Do not retry session creation: the server may have accepted it.
                if not request.resumable_uri or not retryable or failures >= plan["retries"]:
                    raise UploadError("Upload stopped; outcome is uncertain. Inspect the channel before any new upload") from None
                failures += 1
                time.sleep(min(2**(failures - 1), 8))
                continue
            failures = 0
            if response is not None:
                video_id = response.get("id") if isinstance(response, dict) else None
                if not isinstance(video_id, str) or not video_id:
                    raise UploadError("Upload returned no video ID; inspect the channel before any new upload")
                result = {"video_id": video_id, "channel_id": plan["channel_id"], "state": "uploaded",
                          "privacy": plan["body"]["status"]["privacyStatus"], "uploaded_bytes": plan["file"]["bytes"]}
                return result
            current_bytes = status.resumable_progress if status else last_bytes
            stalls = stalls + 1 if current_bytes <= last_bytes else 0
            last_bytes = current_bytes
            if stalls > plan["retries"] + 1:
                raise UploadError("Upload made no progress; inspect the channel before any new upload")
            if status and progress:
                progress(status.resumable_progress, status.total_size)
    except UploadError:
        raise
    except (Exception, KeyboardInterrupt):
        raise UploadError("Upload interrupted; inspect the channel before any new upload",
                          video_id=result["video_id"] if result else None) from None
    finally:
        media.stream().close()
