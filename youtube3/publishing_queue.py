"""Durable single-writer publishing queues with per-channel duplicate protection."""

from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import uuid

from . import artwork, profiles, publishing_batch as batch, publishing_job as jobs

SCHEMA = "youtube3.publishing-queue.v1"
LEDGER_SCHEMA = "youtube3.upload-ledger.v1"


class QueueError(ValueError):
    def __init__(self, message, queue=None):
        self.queue = deepcopy(queue)
        super().__init__(message)


@contextmanager
def locked(path):
    """OS-backed non-blocking lock; process exit releases it on Windows and POSIX."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    if handle.seek(0, os.SEEK_END) == 0:
        handle.write(b"0")
        handle.flush()
    handle.seek(0)
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        raise QueueError("Another publishing runner holds this queue/channel lock") from None
    try:
        yield
    finally:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def _write(document, path, *, overwrite=True):
    artwork.save_bytes(path, (json.dumps(document, indent=2) + "\n").encode("utf-8"), overwrite=overwrite)


def default_ledger(channel_id):
    if not isinstance(channel_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", channel_id):
        raise ValueError("Invalid channel ID")
    return profiles.config_dir().parent / "publishing" / f"uploads-{channel_id}.json"


def fingerprint(spec):
    path = Path(spec["path"])
    before = path.stat()
    if before.st_size != spec["bytes"] or before.st_mtime_ns != spec["modified_ns"]:
        raise QueueError("Media changed after planning; build a new plan")
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    after = path.stat()
    if (after.st_size, after.st_mtime_ns) != (before.st_size, before.st_mtime_ns):
        raise QueueError("Media changed while fingerprinting")
    return digest.hexdigest()


def initialize_queue(plan, path, *, ledger_path=None):
    batch.validate_plan(plan)
    path = Path(path).expanduser().resolve()
    ledger_path = Path(ledger_path or default_ledger(plan["channel_id"])).expanduser().resolve()
    inputs = set()
    hashes, seen = {}, set()
    for entry in plan["entries"]:
        job = entry["job"]
        digest = fingerprint(job["upload"]["file"]) if job["upload"] else None
        if digest and digest in seen:
            raise QueueError("Batch contains duplicate video content; select one entry before running")
        if digest:
            seen.add(digest)
            inputs.add(Path(job["upload"]["file"]["path"]).resolve())
        if job["thumbnail"]:
            inputs.add(Path(job["thumbnail"]["path"]).resolve())
        hashes[entry["id"]] = digest
    artifacts = [path, ledger_path, Path(str(path) + ".pause"), Path(str(path) + ".lock"), Path(str(ledger_path) + ".lock")]
    artifacts.extend(Path(str(path) + ".jobs") / (entry["id"] + ".json") for entry in plan["entries"])
    if (len(set(artifacts)) != len(artifacts) or set(artifacts) & inputs
            or any(a in b.parents for a in artifacts for b in artifacts if a != b)):
        raise QueueError("Queue/ledger/checkpoint paths must differ from each other and from media inputs")
    queue = {"schema": SCHEMA, "id": uuid.uuid4().hex, "plan": deepcopy(plan), "ledger": str(ledger_path),
             "fingerprints": hashes, "state": "pending", "entries": {entry["id"]: {"state": "pending", "video_id": entry["job"]["video_id"],
             "playlists": {value: "pending" for value in entry["playlists"]}, "error": None} for entry in plan["entries"]}}
    _write(queue, path, overwrite=False)
    return queue


def load_queue(path):
    with Path(path).open(encoding="utf-8") as source:
        queue = json.load(source)
    if not isinstance(queue, dict) or set(queue) != {"schema", "id", "plan", "ledger", "fingerprints", "state", "entries"} or queue.get("schema") != SCHEMA:
        raise QueueError("Unsupported publishing queue schema/fields")
    batch.validate_plan(queue["plan"])
    ids = {entry["id"] for entry in queue["plan"]["entries"]}
    if not isinstance(queue["entries"], dict) or set(queue["entries"]) != ids or set(queue["fingerprints"]) != ids:
        raise QueueError("Queue mappings differ from its fixed plan")
    if not isinstance(queue["id"], str) or not re.fullmatch(r"[a-f0-9]{32}", queue["id"]) or not isinstance(queue["ledger"], str):
        raise QueueError("Invalid queue identity/ledger")
    for entry in queue["plan"]["entries"]:
        result = queue["entries"][entry["id"]]
        if not isinstance(result, dict) or set(result) != {"state", "video_id", "playlists", "error"}:
            raise QueueError("Invalid queue result fields")
        if set(result["playlists"]) != set(entry["playlists"]):
            raise QueueError("Queue playlist mapping changed")
        if result["state"] not in ("pending", "running", "paused", "completed", "failed", "blocked", "duplicate"):
            raise QueueError("Invalid queue entry state")
        if any(value not in ("pending", "running", "successful", "unknown") for value in result["playlists"].values()):
            raise QueueError("Invalid playlist result state")
        digest = queue["fingerprints"][entry["id"]]
        if digest is not None and (not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest)):
            raise QueueError("Invalid media fingerprint")
        if bool(entry["job"]["upload"]) != (digest is not None):
            raise QueueError("Upload entry is missing its fingerprint")
    return queue


def _ledger(queue):
    path = Path(queue["ledger"])
    if not path.exists():
        return {"schema": LEDGER_SCHEMA, "channel_id": queue["plan"]["channel_id"], "uploads": {}}
    with path.open(encoding="utf-8") as source:
        value = json.load(source)
    if not isinstance(value, dict) or set(value) != {"schema", "channel_id", "uploads"} or value.get("schema") != LEDGER_SCHEMA or value["channel_id"] != queue["plan"]["channel_id"]:
        raise QueueError("Upload ledger belongs to another channel or has an unsupported schema")
    if not isinstance(value["uploads"], dict):
        raise QueueError("Invalid upload ledger")
    for digest, record in value["uploads"].items():
        if not re.fullmatch(r"[a-f0-9]{64}", digest) or not isinstance(record, dict) or set(record) != {"queue_id", "entry", "state", "video_id"}:
            raise QueueError("Invalid upload ledger record")
        if record["state"] not in ("reserved", "unknown", "uploaded") or (record["state"] == "uploaded" and not record["video_id"]):
            raise QueueError("Invalid upload ledger state")
    return value


def _record(queue, ledger, identity, state, video_id=None):
    digest = queue["fingerprints"][identity]
    if digest:
        prior = ledger["uploads"].get(digest)
        if prior and prior["video_id"] and prior["video_id"] != video_id:
            raise QueueError("Content fingerprint already names another uploaded video", queue)
        ledger["uploads"][digest] = {"queue_id": queue["id"], "entry": identity, "state": state, "video_id": video_id}
        _write(ledger, queue["ledger"])


def _job_path(path, identity):
    return Path(str(Path(path).resolve()) + ".jobs") / (identity + ".json")


def request_pause(path):
    load_queue(path)
    flag = Path(str(Path(path).resolve()) + ".pause")
    try:
        artwork.save_bytes(flag, b"pause\n")
    except FileExistsError:
        pass  # A concurrent or previous caller already requested the pause.


def status(path):
    queue = load_queue(path)
    return {"state": queue["state"], "channel_id": queue["plan"]["channel_id"], "entries": queue["entries"]}


def run_queue(client, path, *, resume=False, retry=False, select=None, stage=None, limit=None, continue_on_error=False):
    path = Path(path).resolve()
    queue = load_queue(path)
    if stage is not None and (not retry or stage not in (*jobs.STAGES, "playlist")):
        raise QueueError("Stage selection requires retry and a valid stage")
    if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int) or limit < 1):
        raise QueueError("limit must be a positive integer")
    if select is not None and (not select or set(select) - set(queue["entries"])):
        raise QueueError("Unknown/empty queue entry selection")
    if client.signed_in_channel()["id"] != queue["plan"]["channel_id"] or client.profile != queue["plan"]["profile"]:
        raise QueueError("Selected channel/profile differs from the queue")
    pause = Path(str(path) + ".pause")
    with locked(str(queue["ledger"]) + ".lock"), locked(str(path) + ".lock"):
        queue = load_queue(path)
        ledger = _ledger(queue)
        if resume:
            pause.unlink(missing_ok=True)
        queue["state"] = "running"
        processed = 0
        for entry in queue["plan"]["entries"]:
            identity, result = entry["id"], queue["entries"][entry["id"]]
            if select is not None and identity not in select:
                continue
            if result["state"] in ("completed", "duplicate") or (result["state"] in ("failed", "blocked") and not retry):
                continue
            if pause.exists() or (limit is not None and processed >= limit):
                queue["state"] = "paused"
                break
            child_path = _job_path(path, identity)
            job = jobs.load_job(child_path) if child_path.exists() else deepcopy(entry["job"])
            if stage is not None and (job.get("failed_stage") != stage if stage != "playlist" else result["error"] != "playlist"):
                raise QueueError("Selected entry did not fail at the requested stage", queue)
            digest = queue["fingerprints"][identity]
            record = ledger["uploads"].get(digest) if digest else None
            if job["video_id"]:
                _record(queue, ledger, identity, "uploaded", job["video_id"])
            elif record and (record["queue_id"], record["entry"]) != (queue["id"], identity):
                result.update(state="duplicate" if record["video_id"] else "blocked", video_id=record["video_id"], error="duplicate_content")
                _write(queue, path)
                continue
            elif record and not record["video_id"]:
                result.update(state="blocked", error="upload")
                queue["state"] = "blocked"
                _write(queue, path)
                if not continue_on_error:
                    break
                continue
            elif record and record["video_id"]:
                # Only this entry's durable record may recover a missed queue checkpoint.
                job["video_id"] = record["video_id"]
                job["stages"]["upload"] = "successful"
                if child_path.exists():
                    jobs._persist(job, child_path, overwrite=True)

            def before(current_stage, current_job, *, result=result, digest=digest, identity=identity):
                if pause.exists():
                    return False
                if current_stage == "publication" and any(value != "successful" for value in result["playlists"].values()):
                    return False
                if current_stage == "upload":
                    if fingerprint(current_job["upload"]["file"]) != digest:
                        raise QueueError("Media content changed after queue initialization", queue)
                    prior = ledger["uploads"].get(digest)
                    if prior and prior["state"] in ("uploaded", "unknown"):
                        raise QueueError("Upload is known or uncertain; explicit recovery is required", queue)
                    _record(queue, ledger, identity, "reserved")
                return True

            def after(current_stage, current_job, *, result=result, identity=identity):
                result["video_id"] = current_job["video_id"]
                if current_stage == "upload":
                    _record(queue, ledger, identity, "uploaded", current_job["video_id"])
                _write(queue, path)

            result.update(state="running", error=None)
            _write(queue, path)
            try:
                job = jobs.apply_publishing_job(client, job, child_path, resume=child_path.exists(), before_stage=before, after_stage=after)
                result["video_id"] = job["video_id"]
                if pause.exists():
                    result["state"], queue["state"] = "paused", "paused"
                    _write(queue, path)
                    break
                for playlist_id, membership in list(result["playlists"].items()):
                    if membership == "successful":
                        continue
                    if pause.exists():
                        break
                    uncertain = membership in ("running", "unknown")
                    result["playlists"][playlist_id] = "running"
                    _write(queue, path)
                    try:
                        membership_result = batch.ensure_playlist_member(client, playlist_id, job["video_id"], allow_insert=not uncertain)
                    except (Exception, KeyboardInterrupt):
                        result["playlists"][playlist_id] = "unknown"
                        result["error"] = "playlist"
                        raise QueueError("Playlist result is uncertain; inspect before retry", queue) from None
                    if membership_result["state"] == "unknown":
                        result["playlists"][playlist_id] = "unknown"
                        result["error"] = "playlist"
                        raise QueueError("Prior playlist change is not visible; explicit missing-membership confirmation is required", queue)
                    result["playlists"][playlist_id] = "successful"
                    _write(queue, path)
                if pause.exists():
                    result["state"], queue["state"] = "paused", "paused"
                    _write(queue, path)
                    break
                if job["state"] == "paused":
                    job = jobs.apply_publishing_job(client, jobs.load_job(child_path), child_path, resume=True, before_stage=before, after_stage=after)
                result["state"] = "completed" if job["state"] == "completed" else "paused"
            except (Exception, KeyboardInterrupt) as error:
                current = error.job if isinstance(error, jobs.PublishingJobError) else (jobs.load_job(child_path) if child_path.exists() else job)
                result["video_id"] = current["video_id"]
                if current["video_id"]:
                    try:
                        _record(queue, ledger, identity, "uploaded", current["video_id"])
                    except OSError:
                        raise QueueError(f"Ledger checkpoint failed; known video ID: {current['video_id']}", queue) from None
                elif digest and current["stages"]["upload"] in ("running", "unknown"):
                    _record(queue, ledger, identity, "unknown")
                result["state"] = "blocked" if current["state"] == "recovery_required" else "failed"
                result["error"] = result["error"] or current.get("failed_stage") or "checkpoint"
                queue["state"] = "failed"
                try:
                    _write(queue, path)
                except OSError:
                    raise QueueError(f"Queue checkpoint failed; known video ID: {result['video_id'] or 'unknown'}", queue) from None
                if not continue_on_error:
                    break
            processed += 1
        if queue["state"] == "running":
            values = [entry["state"] for entry in queue["entries"].values()]
            if all(value in ("completed", "duplicate") for value in values):
                queue["state"] = "completed"
            elif any(value in ("failed", "blocked") for value in values):
                queue["state"] = "failed" if "failed" in values else "blocked"
            else:
                queue["state"] = "paused" if "paused" in values else "pending"
        _write(queue, path)
        return queue


def recover_entry(client, path, identity, *, video_id=None, missing_playlist=None, confirm_not_uploaded=False):
    """Explicit local recovery, after the operator inspects an uncertain outcome."""
    path = Path(path).resolve()
    queue = load_queue(path)
    if identity not in queue["entries"] or sum((video_id is not None, missing_playlist is not None, confirm_not_uploaded)) != 1:
        raise QueueError("Select an entry and one explicit recovery action")
    if client.signed_in_channel()["id"] != queue["plan"]["channel_id"] or client.profile != queue["plan"]["profile"]:
        raise QueueError("Selected channel/profile differs from the queue")
    with locked(str(queue["ledger"]) + ".lock"), locked(str(path) + ".lock"):
        queue = load_queue(path)
        result = queue["entries"][identity]
        if confirm_not_uploaded:
            entry = next(value for value in queue["plan"]["entries"] if value["id"] == identity)
            child_path = _job_path(path, identity)
            job = jobs.load_job(child_path) if child_path.exists() else deepcopy(entry["job"])
            ledger = _ledger(queue)
            digest = queue["fingerprints"][identity]
            record = ledger["uploads"].get(digest) if digest else None
            if not digest or job["video_id"] or result["video_id"] or (record and record["video_id"]):
                raise QueueError("A known upload cannot be reset")
            if record and (record["queue_id"], record["entry"]) != (queue["id"], identity):
                raise QueueError("Recover the queue that reserved this content first")
            job["stages"]["upload"], job["state"], job["failed_stage"] = "pending", "planned", None
            jobs._persist(job, child_path, overwrite=child_path.exists())
            if record:
                del ledger["uploads"][digest]
                _write(ledger, queue["ledger"])
        elif video_id:
            jobs._owner(client, video_id, queue["plan"]["channel_id"])
            entry = next(value for value in queue["plan"]["entries"] if value["id"] == identity)
            child_path = _job_path(path, identity)
            job = jobs.load_job(child_path) if child_path.exists() else deepcopy(entry["job"])
            if job["video_id"] and job["video_id"] != video_id:
                raise QueueError("A known uploaded ID cannot be replaced")
            job["video_id"] = video_id
            if job["upload"]:
                job["stages"]["upload"] = "successful"
            job["state"], job["failed_stage"] = "paused", None
            jobs._persist(job, child_path, overwrite=child_path.exists())
            _record(queue, _ledger(queue), identity, "uploaded", video_id)
            result["video_id"] = video_id
        else:
            if result["playlists"].get(missing_playlist) not in ("running", "unknown"):
                raise QueueError("Selected playlist does not have an uncertain result")
            result["playlists"][missing_playlist] = "pending"
        result.update(state="paused", error=None)
        queue["state"] = "paused"
        _write(queue, path)
    return queue
