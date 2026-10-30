import json
import sys
from urllib.parse import urlparse

import pytest
from googleapiclient.discovery import build
from googleapiclient.http import HttpMockSequence
from PIL import Image

from youtube3 import YoutubeClient, publishing_job as jobs
from youtube3.cli import publish_job

SESSION = "https://upload.example.invalid/synthetic-session"


def response(body=None, status=200, **headers):
    return ({"status": str(status), **headers}, json.dumps(body) if body is not None else "")


def video(title="Old", privacy="private"):
    return {"id": "new-video", "snippet": {"channelId": "UCmine", "title": title, "description": "Original",
            "categoryId": "22", "tags": ["preserve"], "defaultLanguage": "en"},
            "status": {"privacyStatus": privacy, "embeddable": False, "license": "creativeCommon"}}


def resource(title="Old", privacy="private"):
    return response({"items": [video(title, privacy)]})


def prepared(*responses):
    http = HttpMockSequence(list(responses))
    client = YoutubeClient(service=build("youtube", "v3", http=http, developerKey="test-key"))
    client._channel = {"id": "UCmine", "title": "Mine"}
    return client, http


@pytest.fixture
def inputs(tmp_path):
    media = tmp_path / "video.mp4"
    media.write_bytes(b"synthetic video")
    image = tmp_path / "thumbnail.png"
    Image.new("RGB", (1280, 720), "navy").save(image)
    return media, image, tmp_path / "job.json"


def upload_responses():
    return (response(location=SESSION), response({"id": "new-video"}))


def writes(http):
    return [(urlparse(uri).path, method, body) for uri, method, body, headers in http.request_sequence if method != "GET"]


def test_complete_job_stage_order_private_upload_and_metadata_preservation(inputs):
    media, image, path = inputs
    client, http = prepared(response({"items": [{"status": {"longUploadsStatus": "allowed"}}]}),
        *upload_responses(), response({"items": []}), resource(), response(video("New")),
        resource("New"), response(video("New", "public")))
    job = jobs.plan_publishing_job(client, file=media, title="New", thumbnail=image, privacy="public")
    assert not path.exists()
    assert job["upload"]["body"]["status"]["privacyStatus"] == "private"
    complete = jobs.apply_publishing_job(client, job, path)
    assert complete["state"] == "completed"
    assert all(state == "successful" for state in complete["stages"].values())
    calls = writes(http)
    assert [(p, m) for p, m, _ in calls] == [
        ("/upload/youtube/v3/videos", "POST"), ("/synthetic-session", "PUT"),
        ("/upload/youtube/v3/thumbnails/set", "POST"), ("/youtube/v3/videos", "PUT"), ("/youtube/v3/videos", "PUT")]
    metadata = json.loads(calls[-2][2])
    assert metadata["snippet"]["tags"] == ["preserve"]
    assert metadata["snippet"]["defaultLanguage"] == "en"
    status = json.loads(calls[-1][2])["status"]
    assert status == {"privacyStatus": "public", "embeddable": False, "license": "creativeCommon"}
    saved = path.read_text(encoding="utf-8")
    assert SESSION not in saved
    assert jobs.load_job(path) == complete


@pytest.mark.parametrize("stage", ["thumbnail", "metadata", "publication"])
def test_post_upload_failures_resume_known_id_without_upload(inputs, stage):
    media, image, path = inputs
    failure = response({"error": {"code": 403, "message": SESSION}}, status=403)
    sequence = [response({"items": [{"status": {"longUploadsStatus": "allowed"}}]}), *upload_responses()]
    if stage == "thumbnail":
        sequence += [failure]
    elif stage == "metadata":
        sequence += [response({}), resource(), failure]
    else:
        sequence += [response({}), resource(), response(video("New")), resource("New"), failure]
    client, http = prepared(*sequence)
    job = jobs.plan_publishing_job(client, file=media, title="New", thumbnail=image, privacy="public")
    with pytest.raises(jobs.PublishingJobError) as result:
        jobs.apply_publishing_job(client, job, path)
    assert result.value.video_id == "new-video"
    saved = jobs.load_job(path)
    assert saved["failed_stage"] == stage
    assert saved["stages"]["upload"] == "successful"
    assert SESSION not in str(result.value) and SESSION not in path.read_text(encoding="utf-8")
    # The original upload media can disappear; later stages still use the ID.
    media.unlink()
    resume_responses = [resource()]
    if stage == "thumbnail":
        resume_responses += [response({})]
    if stage in ("thumbnail", "metadata"):
        resume_responses += [resource(), response(video("New"))]
    resume_responses += [resource("New"), response(video("New", "public"))]
    second, second_http = prepared(*resume_responses)
    complete = jobs.apply_publishing_job(second, saved, path, resume=True)
    assert complete["state"] == "completed"
    assert not any(method == "POST" and endpoint.endswith("/videos") for endpoint, method, body in writes(second_http))
    if stage == "publication":
        assert len(writes(second_http)) == 1


def test_checkpoint_failure_immediately_after_upload_exposes_id_and_requires_recovery(inputs, monkeypatch):
    media, _, path = inputs
    client, http = prepared(*upload_responses())
    job = jobs.plan_publishing_job(client, file=media, title="New")
    original = jobs.artwork.save_bytes
    calls = 0

    def fail_after_upload(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise OSError("disk full")
        return original(*args, **kwargs)

    monkeypatch.setattr(jobs.artwork, "save_bytes", fail_after_upload)
    with pytest.raises(jobs.PublishingJobError) as result:
        jobs.apply_publishing_job(client, job, path)
    assert result.value.video_id == "new-video"
    assert "new-video" in str(result.value)
    saved = jobs.load_job(path)
    assert saved["video_id"] is None and saved["stages"]["upload"] == "running"
    second, second_http = prepared()
    with pytest.raises(jobs.PublishingJobError, match="unknown"):
        jobs.apply_publishing_job(second, saved, path, resume=True)
    assert not second_http.request_sequence
    saved = jobs.load_job(path)
    third, third_http = prepared(resource("New"), resource("New"), resource("New"))
    complete = jobs.apply_publishing_job(third, saved, path, resume=True, recover_video_id="new-video")
    assert complete["state"] == "completed"
    assert all(method == "GET" for uri, method, body, headers in third_http.request_sequence)


def test_unknown_upload_outcome_never_resumed_automatically(inputs):
    media, _, path = inputs
    client, http = prepared(response({"error": {"code": 503, "message": SESSION}}, status=503))
    job = jobs.plan_publishing_job(client, file=media, title="New")
    with pytest.raises(jobs.PublishingJobError):
        jobs.apply_publishing_job(client, job, path)
    saved = jobs.load_job(path)
    assert saved["state"] == "recovery_required"
    second, second_http = prepared()
    with pytest.raises(jobs.PublishingJobError, match="unknown"):
        jobs.apply_publishing_job(second, saved, path, resume=True)
    assert not second_http.request_sequence
    assert len(http.request_sequence) == 1


def test_studio_video_never_uploads_and_job_preview_no_changes(inputs):
    _, _, path = inputs
    client, http = prepared(resource(), resource(), resource(), resource(), response(video("New")))
    job = jobs.plan_publishing_job(client, video_id="new-video", title="New")
    assert job["stages"]["upload"] == "skipped"
    assert all(method == "GET" for uri, method, body, headers in http.request_sequence)
    assert not path.exists()
    complete = jobs.apply_publishing_job(client, job, path)
    assert complete["state"] == "completed"
    assert len(writes(http)) == 1 and writes(http)[0][1] == "PUT"


def test_initial_checkpoint_failure_prevents_any_upload(inputs, monkeypatch):
    media, _, path = inputs
    client, http = prepared()
    job = jobs.plan_publishing_job(client, file=media, title="New")
    monkeypatch.setattr(jobs.artwork, "save_bytes", lambda *a, **kw: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(jobs.PublishingJobError, match="Checkpoint"):
        jobs.apply_publishing_job(client, job, path)
    assert not http.request_sequence


def test_cli_preview_no_checkpoint_or_upload(inputs, monkeypatch, capsys):
    media, _, path = inputs
    client, http = prepared()
    monkeypatch.setattr(publish_job, "client", lambda args: client)
    monkeypatch.setattr(sys, "argv", ["publishing", "--file", str(media), "--title", "New", "--job", str(path)])
    publish_job.main()
    assert "Dry run" in capsys.readouterr().out
    assert not path.exists() and not http.request_sequence


def test_scheduling_changes_status_only_after_metadata(inputs):
    _, _, path = inputs
    client, http = prepared(resource(), resource(), resource(), resource(), response(video()))
    job = jobs.plan_publishing_job(client, video_id="new-video", publish_at="2099-01-01T00:00:00Z")
    complete = jobs.apply_publishing_job(client, job, path)
    status = json.loads(writes(http)[-1][2])["status"]
    assert status["publishAt"] == "2099-01-01T00:00:00Z"
    assert status["privacyStatus"] == "private" and status["embeddable"] is False
    assert complete["stages"]["publication"] == "successful"


def test_checkpoint_rejects_unknown_fields(inputs):
    media, _, path = inputs
    client, _ = prepared()
    job = jobs.plan_publishing_job(client, file=media, title="New")
    job["credentials"] = {}
    path.write_text(json.dumps(job), encoding="utf-8")
    with pytest.raises(ValueError, match="fields"):
        jobs.load_job(path)


def test_interruption_after_upload_keeps_id_and_blocks_publication(inputs, monkeypatch):
    media, image, path = inputs
    client, http = prepared(response({"items": [{"status": {"longUploadsStatus": "allowed"}}]}),
                            *upload_responses())
    job = jobs.plan_publishing_job(client, file=media, title="New", thumbnail=image, privacy="public")

    def interrupted(*args):
        raise KeyboardInterrupt

    monkeypatch.setattr(client, "upload_thumbnail", interrupted)
    with pytest.raises(jobs.PublishingJobError) as result:
        jobs.apply_publishing_job(client, job, path)
    assert result.value.video_id == "new-video"
    saved = jobs.load_job(path)
    assert saved["stages"]["thumbnail"] == "failed"
    assert saved["stages"]["publication"] == "pending"
    assert len(writes(http)) == 2


def test_schedule_failure_keeps_private_video_and_known_id(inputs):
    _, _, path = inputs
    client, http = prepared(resource(), resource(), resource(), resource(),
                           response({"error": {"code": 400, "message": "Invalid schedule"}}, status=400))
    job = jobs.plan_publishing_job(client, video_id="new-video", publish_at="2099-01-01T00:00:00Z")
    with pytest.raises(jobs.PublishingJobError) as result:
        jobs.apply_publishing_job(client, job, path)
    assert result.value.video_id == "new-video"
    assert jobs.load_job(path)["stages"]["publication"] == "failed"
    assert json.loads(writes(http)[0][2])["status"]["privacyStatus"] == "private"
