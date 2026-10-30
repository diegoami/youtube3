"""Checkpointed upload, thumbnail, metadata and publication of one video."""

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path

from . import artwork, publish, upload, publishing_metadata
from .thumbnail_batch import checked_image

SCHEMA = "youtube3.publishing-job.v1"
STAGES = ("upload", "thumbnail", "metadata", "publication")
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
                        public_stats_viewable=None, contains_synthetic_media=None):
    """Preview all four stages; no files/uploads/account changes are made.

    New uploads start private. Public/unlisted visibility or scheduling is the
    final stage, after thumbnail and metadata have succeeded.
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
    return {"schema": SCHEMA, "channel_id": channel_id, "profile": client.profile,
            "video_id": video_id, "upload": upload_plan, "thumbnail": image, "metadata": metadata,
            "publication": {"privacy": privacy, "publish_at": publish_at},
            "stages": {"upload": "pending" if upload_plan else "skipped",
                       "thumbnail": "pending" if image else "skipped",
                       "metadata": "pending" if any(value is not None for value in metadata.values()) else "skipped",
                       "publication": "pending" if privacy is not None or publish_at is not None else "skipped"},
            "state": "planned", "failed_stage": None}


def validate_job(job):
    """Allowlist checkpoint fields; credentials, API responses and session URLs have no slot."""
    if not isinstance(job, dict) or set(job) != JOB_KEYS or job.get("schema") != SCHEMA:
        raise ValueError("Unsupported publishing job schema/fields")
    if not isinstance(job["stages"], dict) or set(job["stages"]) != set(STAGES):
        raise ValueError("Invalid publishing stages")
    if any(value not in STATES for value in job["stages"].values()):
        raise ValueError("Invalid publishing stage state")
    if job["state"] not in ("planned", "running", "failed", "recovery_required", "completed", "paused"):
        raise ValueError("Invalid publishing job state")
    if job["profile"] is not None and not isinstance(job["profile"], str):
        raise ValueError("Invalid job profile")
    if job["failed_stage"] is not None and job["failed_stage"] not in STAGES:
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


def apply_publishing_job(client, job, path, *, resume=False, recover_video_id=None, before_stage=None, after_stage=None):
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
    if any(path.resolve() == Path(media).resolve() for media in protected):
        raise PublishingJobError("Checkpoint must differ from media inputs", job)
    if resume:
        if load_job(path) != job:
            raise PublishingJobError("Checkpoint changed; load it again", job)
    elif recover_video_id:
        raise PublishingJobError("Recovery requires an existing checkpoint", job)
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
        if job["stages"][stage] in ("successful", "skipped"):
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
