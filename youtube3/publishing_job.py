"""Checkpointed upload, thumbnail, metadata, subtitles and publication of one video."""

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import re

from . import artwork, publish, upload, publishing_metadata, captions
from .thumbnail_batch import checked_image

SCHEMA = "youtube3.publishing-job.v1"
SUBTITLE_SCHEMA = "youtube3.publishing-job.v2"
LEGACY_STAGES = ("upload", "thumbnail", "metadata", "publication")
STAGES = ("upload", "thumbnail", "metadata", "subtitles", "publication")
STATES = {"pending", "running", "successful", "skipped", "failed", "unknown"}
JOB_KEYS = {"schema", "channel_id", "profile", "video_id", "upload", "thumbnail", "metadata", "publication",
            "stages", "state", "failed_stage"}


class PublishingJobError(ValueError):
    """A stopped job; job/video_id remain available even when the checkpoint failed."""

    def __init__(self, message, job):
        self.job = deepcopy(job)
        self.video_id = job.get("video_id")
        suffix = f"; video ID: {self.video_id}" if self.video_id else ""
        super().__init__(message + suffix)


def _owner(client, video_id, channel_id):
    details = client.video_details([video_id])
    if details.get(video_id, {}).get("snippet", {}).get("channelId") != channel_id:
        raise ValueError("Video is missing or belongs to another channel")


def plan_publishing_job(client, *, file=None, video_id=None, title=None, description=None, tags=None,
                        thumbnail=None, privacy=None, publish_at=None, category_id=None, made_for_kids=None,
                        retries=3, chunk_size=upload.DEFAULT_CHUNK_SIZE, notify_subscribers=False,
                        default_language=None, default_audio_language=None, license=None, embeddable=None,
                        public_stats_viewable=None, contains_synthetic_media=None, subtitles=None):
    """Preview all requested stages; no files/uploads/account changes are made.

    New uploads start private. Public/unlisted visibility or scheduling is the
    final stage, after thumbnail, metadata and requested subtitles have succeeded.
    """
    if (file is None) == (video_id is None):
        raise ValueError("Give either a local video file or an existing video ID")
    channel_id = client.signed_in_channel()["id"]
    if privacy is not None and privacy not in publish.PRIVACY:
        raise ValueError("Privacy must be private, unlisted or public")
    if publish_at is not None:
        when = publish._when(publish_at)
        if when <= datetime.now(timezone.utc):
            raise ValueError("Scheduled publication must be in the future")
        if privacy not in (None, "private"):
            raise ValueError("A scheduled video must remain private until publication")
        publish_at = when.isoformat().replace("+00:00", "Z")
    metadata = {"title": title, "description": description, "tags": tags}
    extra_options = dict(category_id=category_id, made_for_kids=made_for_kids, default_language=default_language,
                         default_audio_language=default_audio_language, license=license, embeddable=embeddable,
                         public_stats_viewable=public_stats_viewable, contains_synthetic_media=contains_synthetic_media)
    publishing_metadata.parts(extra_options)
    metadata.update({key: value for key, value in extra_options.items() if value is not None})
    subtitle_rows = plan_subtitles(client, subtitles, video_id=video_id)
    image = checked_image(thumbnail) if thumbnail is not None else None
    upload_plan = None
    if file is not None:
        upload_plan = upload.plan_video_upload(client, file, title=title, description=description or "",
            tags=tags, category_id=category_id or "22", privacy="private", made_for_kids=made_for_kids, retries=retries,
            chunk_size=chunk_size, notify_subscribers=notify_subscribers,
            **{key: value for key, value in extra_options.items() if key not in ("category_id", "made_for_kids")})
    else:
        _owner(client, video_id, channel_id)
        checked = publish.plan_publish(client, video_id, **metadata, privacy=privacy, publish_at=publish_at)
        if checked["errors"]:
            raise ValueError("; ".join(checked["errors"]))
    if image:
        channels = client.youtube.channels().list(part="status", mine=True).execute().get("items", [])
        if not channels or channels[0].get("status", {}).get("longUploadsStatus") != "allowed":
            raise ValueError("Custom thumbnails require a verified eligible channel")
    job = {"schema": SCHEMA, "channel_id": channel_id, "profile": client.profile,
            "video_id": video_id, "upload": upload_plan, "thumbnail": image, "metadata": metadata,
            "publication": {"privacy": privacy, "publish_at": publish_at},
            "stages": {"upload": "pending" if upload_plan else "skipped",
                       "thumbnail": "pending" if image else "skipped",
                       "metadata": "pending" if any(value is not None for value in metadata.values()) else "skipped",
                       "publication": "pending" if privacy is not None or publish_at is not None else "skipped"},
            "state": "planned", "failed_stage": None}
    if subtitle_rows:
        job.update(schema=SUBTITLE_SCHEMA, subtitles=subtitle_rows)
        job["stages"]["subtitles"] = "pending"
        job["stages"] = {stage: job["stages"][stage] for stage in STAGES}
    return job


def validate_job(job):
    """Allowlist checkpoint fields; credentials, API responses and session URLs have no slot."""
    if not isinstance(job, dict) or job.get("schema") not in (SCHEMA, SUBTITLE_SCHEMA):
        raise ValueError("Unsupported publishing job schema/fields")
    with_subtitles = job["schema"] == SUBTITLE_SCHEMA
    if set(job) != JOB_KEYS | ({"subtitles"} if with_subtitles else set()):
        raise ValueError("Unsupported publishing job schema/fields")
    if with_subtitles:
        validate_subtitles(job["subtitles"])
    if not isinstance(job["stages"], dict) or set(job["stages"]) != set(STAGES if with_subtitles else LEGACY_STAGES):
        raise ValueError("Invalid publishing stages")
    if with_subtitles and job["stages"]["subtitles"] in ("successful", "skipped") and any(row["state"] != "successful" for row in job["subtitles"]):
        raise ValueError("Subtitle stage cannot skip unfinished tracks")
    if any(value not in STATES for value in job["stages"].values()):
        raise ValueError("Invalid publishing stage state")
    if job["state"] not in ("planned", "running", "failed", "recovery_required", "completed", "paused"):
        raise ValueError("Invalid publishing job state")
    if job["profile"] is not None and not isinstance(job["profile"], str):
        raise ValueError("Invalid job profile")
    if job["failed_stage"] is not None and job["failed_stage"] not in job["stages"]:
        raise ValueError("Invalid failed stage")
    if not isinstance(job["channel_id"], str) or not job["channel_id"]:
        raise ValueError("Job must identify its destination channel")
    if job["video_id"] is not None and (not isinstance(job["video_id"], str) or not job["video_id"]):
        raise ValueError("Invalid publishing video ID")
    if (not isinstance(job["metadata"], dict) or not {"title", "description", "tags"} <= set(job["metadata"])
            or set(job["metadata"]) - ({"title", "description", "tags"} | publishing_metadata.FIELDS)):
        raise ValueError("Invalid publishing metadata fields")
    if not isinstance(job["publication"], dict) or set(job["publication"]) != {"privacy", "publish_at"}:
        raise ValueError("Invalid publication fields")
    if job["thumbnail"] is not None and (not isinstance(job["thumbnail"], dict) or
            set(job["thumbnail"]) != {"path", "sha256", "bytes", "width", "height"}):
        raise ValueError("Invalid thumbnail fields")
    spec = job["upload"]
    if spec is not None:
        if not isinstance(spec, dict) or set(spec) != {"file", "body", "notify_subscribers", "retries", "chunk_size", "quota", "channel_id", "profile"}:
            raise ValueError("Invalid upload plan fields")
        if set(spec["file"]) != {"path", "bytes", "modified_ns", "type"} or set(spec["body"]) != {"snippet", "status"}:
            raise ValueError("Invalid upload input fields")
        if set(spec["body"]["snippet"]) - {"title", "description", "categoryId", "tags", "defaultLanguage", "defaultAudioLanguage"}:
            raise ValueError("Invalid upload metadata fields")
        if set(spec["body"]["status"]) - {"privacyStatus", "selfDeclaredMadeForKids", "license", "embeddable", "publicStatsViewable", "containsSyntheticMedia"}:
            raise ValueError("Invalid upload status fields")
        if spec["body"]["status"].get("privacyStatus") != "private":
            raise ValueError("Publishing jobs must upload privately")
        if spec["quota"] != {"bucket": "Video Uploads", "units": 1}:
            raise ValueError("Invalid upload quota fields")
    elif job["video_id"] is None:
        raise ValueError("Job has neither an upload nor an existing video")
    return job


def load_job(path):
    return validate_job(json.loads(Path(path).read_text(encoding="utf-8")))


def _persist(job, path, *, overwrite):
    validate_job(job)
    try:
        artwork.save_bytes(path, (json.dumps(job, indent=2) + "\n").encode("utf-8"), overwrite=overwrite)
    except OSError:
        raise PublishingJobError("Checkpoint failed; inspect the returned job before recovery", job) from None


def _publish(client, job, *, metadata=False):
    options = job["metadata"] if metadata else job["publication"]
    plan = publish.plan_publish(client, job["video_id"], **options)
    if plan["errors"]:
        raise ValueError("Publishing plan failed validation")
    return publish.apply_publish(client, plan)


def apply_publishing_job(client, job, path, *, resume=False, recover_video_id=None, before_stage=None, after_stage=None,
                         recover_subtitle_index=None, recover_caption_id=None, confirm_subtitle_missing=False):
    """Apply/checkpoint each stage. Never reupload a known or uncertain video.

    Resume with a known ID never needs the original media again. An upload left
    running/unknown with no ID needs an explicitly recovered, ownership-checked ID.
    """
    job = deepcopy(validate_job(job))
    path = Path(path).expanduser().absolute()
    channel_id = client.signed_in_channel()["id"]
    if channel_id != job["channel_id"] or client.profile != job["profile"]:
        raise PublishingJobError("Selected channel/profile differs from the job", job)
    protected = []
    if job["upload"]:
        protected.append(job["upload"]["file"]["path"])
    if job["thumbnail"]:
        protected.append(job["thumbnail"]["path"])
    protected.extend(subtitle_inputs(job))
    if any(path.resolve() == Path(media).resolve() for media in protected):
        raise PublishingJobError("Checkpoint must differ from media inputs", job)
    if resume:
        if load_job(path) != job:
            raise PublishingJobError("Checkpoint changed; load it again", job)
    elif recover_video_id:
        raise PublishingJobError("Recovery requires an existing checkpoint", job)
    subtitle_recovery = recover_subtitle_index is not None or recover_caption_id is not None or confirm_subtitle_missing
    if subtitle_recovery:
        if not resume:
            raise PublishingJobError("Subtitle recovery requires an existing checkpoint", job)
        job = recover_subtitle(client, job, recover_subtitle_index, caption_id=recover_caption_id,
                               confirm_missing=confirm_subtitle_missing)
    if recover_video_id:
        if job["video_id"] is not None or job["stages"]["upload"] not in ("running", "unknown"):
            raise PublishingJobError("This job does not need upload-ID recovery", job)
        _owner(client, recover_video_id, channel_id)
        job["video_id"] = recover_video_id
        job["stages"]["upload"] = "successful"
        job["state"], job["failed_stage"] = "planned", None
    if job["video_id"]:
        _owner(client, job["video_id"], channel_id)
        if job["upload"]:
            job["stages"]["upload"] = "successful"
    elif job["stages"]["upload"] in ("running", "unknown", "successful", "skipped"):
        job["stages"]["upload"], job["state"] = "unknown", "recovery_required"
        _persist(job, path, overwrite=resume)
        raise PublishingJobError("Upload outcome is unknown; recover its ID explicitly, never reupload automatically", job)
    _persist(job, path, overwrite=resume)
    for stage in STAGES:
        if stage not in job["stages"] or job["stages"][stage] in ("successful", "skipped"):
            continue
        if before_stage is not None and before_stage(stage, deepcopy(job)) is False:
            job["state"] = "paused"
            _persist(job, path, overwrite=True)
            return job
        job["stages"][stage], job["state"], job["failed_stage"] = "running", "running", None
        _persist(job, path, overwrite=True)  # Mark in-flight before any account change.
        try:
            if stage == "upload":
                result = upload.apply_video_upload(client, job["upload"])
                job["video_id"] = result["video_id"]
            elif stage == "thumbnail":
                if checked_image(job["thumbnail"]["path"]) != job["thumbnail"]:
                    raise ValueError("Thumbnail changed after planning")
                client.upload_thumbnail(job["video_id"], job["thumbnail"]["path"])
            elif stage == "metadata":
                _publish(client, job, metadata=True)
            elif stage == "subtitles":
                if not _apply_subtitles(client, job, path, before_write=(
                        (lambda: before_stage("subtitles", deepcopy(job))) if before_stage else None)):
                    job["stages"][stage], job["state"] = "pending", "paused"
                    _persist(job, path, overwrite=True)
                    return job
            else:
                _publish(client, job)
        except (Exception, KeyboardInterrupt) as error:
            if stage == "upload":
                known_id = getattr(error, "video_id", None)
                if known_id:
                    job["video_id"] = known_id
                    job["stages"][stage] = "successful"
                    job["state"] = "failed"
                else:
                    unknown = not isinstance(error, upload.UploadError) or error.outcome != "not_started"
                    job["stages"][stage] = "unknown" if unknown else "failed"
                    job["state"] = "recovery_required" if unknown else "failed"
            elif stage == "subtitles" and any(row["state"] in ("running", "unknown") for row in job["subtitles"]):
                job["stages"][stage], job["state"] = "unknown", "recovery_required"
            else:
                job["stages"][stage], job["state"] = "failed", "failed"
            job["failed_stage"] = stage
            _persist(job, path, overwrite=True)
            raise PublishingJobError(f"Publishing stopped at {stage}; inspect checkpoint before resuming", job) from None
        job["stages"][stage] = "successful"
        _persist(job, path, overwrite=True)  # Record upload ID before doing anything else.
        if after_stage is not None:
            after_stage(stage, deepcopy(job))
    job["state"], job["failed_stage"] = "completed", None
    _persist(job, path, overwrite=True)
    return job


def subtitle_inputs(job):
    return [row["file"]["path"] for row in job.get("subtitles", [])]


def plan_subtitles(client, settings, *, video_id=None):
    if settings is None:
        return []
    if not isinstance(settings, list):
        raise ValueError("subtitles must be a list of track settings")
    rows, seen = [], set()
    for track in settings:
        captions.validate_settings(track)
        track = deepcopy(track)
        spec = captions.check_caption(track["file"])
        track["file"] = spec["path"]
        identity = ("replace", track["caption_id"]) if track.get("caption_id") else ("insert", track["language"], track.get("name", ""))
        if identity in seen:
            raise ValueError("Duplicate subtitle track")
        seen.add(identity)
        if not track.get("caption_id"):
            track.setdefault("name", "")
            if track.get("draft") is None:
                track["draft"] = False
        if video_id:
            options = {key: value for key, value in track.items() if key != "file"}
            preview = captions.plan_caption(client, video_id, track["file"], **options)
            track["draft"] = preview["body"]["snippet"]["isDraft"]
        elif track.get("caption_id"):
            raise ValueError("A new video cannot replace an existing caption ID")
        rows.append({"settings": track, "file": spec, "state": "pending", "caption_id": None})
    return rows


def validate_subtitles(rows):
    if not isinstance(rows, list) or not rows:
        raise ValueError("Invalid subtitle checkpoint")
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"settings", "file", "state", "caption_id"}:
            raise ValueError("Invalid subtitle checkpoint fields")
        captions.validate_settings(row["settings"])
        spec = row["file"]
        if (not isinstance(spec, dict) or set(spec) != captions.FILE_KEYS
                or spec["path"] != row["settings"]["file"]
                or not isinstance(spec["bytes"], int) or isinstance(spec["bytes"], bool) or not 0 < spec["bytes"] <= captions.MAX_BYTES
                or not isinstance(spec["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", spec["sha256"])):
            raise ValueError("Invalid subtitle file fingerprint")
        if row["state"] not in {"pending", "running", "successful", "failed", "unknown"}:
            raise ValueError("Invalid subtitle state")
        if row["caption_id"] is not None and (not isinstance(row["caption_id"], str) or not row["caption_id"]):
            raise ValueError("Invalid accepted caption ID")
        if row["state"] == "successful" and not row["caption_id"]:
            raise ValueError("Successful subtitle needs a caption ID")


def _apply_subtitles(client, job, path, *, before_write=None):
    for row in job["subtitles"]:
        if row["state"] in ("running", "unknown"):
            raise captions.CaptionError("Subtitle outcome is unknown; inspect tracks and recover explicitly", outcome="unknown")
        if row["state"] != "successful" and captions.check_caption(row["file"]["path"]) != row["file"]:
            raise ValueError("Subtitle changed after planning")
    for row in job["subtitles"]:
        if row["state"] == "successful":
            continue
        if before_write is not None and before_write() is False:
            return False
        options = {key: value for key, value in row["settings"].items() if key != "file"}
        plan = captions.plan_caption(client, job["video_id"], row["file"]["path"], **options)
        if plan["file"] != row["file"]:
            raise ValueError("Subtitle changed after planning")
        row["state"] = "running"
        _persist(job, path, overwrite=True)
        try:
            accepted = captions.apply_caption(client, plan)
        except (Exception, KeyboardInterrupt) as error:
            # Validation/known refusal is safe to retry. All other in-flight failures
            # remain uncertain, including interruption and missing response IDs.
            row["state"] = "failed" if isinstance(error, ValueError) and getattr(error, "outcome", "not_started") == "not_started" else "unknown"
            raise
        row.update(state="successful", caption_id=accepted["id"])
        _persist(job, path, overwrite=True)
    return True


def recover_subtitle(client, job, index, *, caption_id=None, confirm_missing=False):
    """Inspect one uncertain 1-based track, then explicitly acknowledge ID or absence.

    ID recovery verifies identity and draft/status metadata, but cannot verify
    subtitle contents; the operator must inspect those in Studio first.
    """
    job = deepcopy(validate_job(job))
    if (isinstance(index, bool) or not isinstance(index, int) or not 1 <= index <= len(job.get("subtitles", []))
            or (caption_id is not None) + bool(confirm_missing) != 1):
        raise ValueError("Select a 1-based subtitle index and exactly one recovered caption ID or missing confirmation")
    if client.profile != job["profile"] or client.signed_in_channel()["id"] != job["channel_id"]:
        raise ValueError("Selected channel/profile differs from the job")
    row = job["subtitles"][index - 1]
    if row["state"] not in ("running", "unknown") or not job["video_id"]:
        raise ValueError("Selected subtitle does not need uncertain-write recovery")
    tracks = captions.list_captions(client, job["video_id"])
    settings = row["settings"]
    if caption_id is not None:
        found = next((track for track in tracks if track["id"] == caption_id), None)
        expected_id = settings.get("caption_id")
        if found is None or (expected_id and caption_id != expected_id):
            raise ValueError("Recovered caption ID does not match this video's track")
        snippet = found["snippet"]
        if not expected_id and (snippet.get("language"), snippet.get("name", "")) != (settings["language"], settings.get("name", "")):
            raise ValueError("Recovered caption language/name differs from the job")
        if snippet.get("status") == "failed" or (settings.get("draft") is not None and snippet.get("isDraft", False) != settings["draft"]):
            raise ValueError("Recovered caption status/draft differs from the job")
        row.update(state="successful", caption_id=caption_id)
    else:
        if settings.get("caption_id"):
            raise ValueError("Replacement recovery requires its inspected caption ID")
        if any((track["snippet"].get("language"), track["snippet"].get("name", "")) == (settings["language"], settings.get("name", "")) for track in tracks):
            raise ValueError("Subtitle track is visible; recover its ID instead of confirming missing")
        row.update(state="pending", caption_id=None)
    job["stages"]["subtitles"], job["state"], job["failed_stage"] = "pending", "paused", None
    return job
