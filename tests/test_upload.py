import json
import sys

import pytest
from googleapiclient.discovery import build
from googleapiclient.http import HttpMockSequence

from youtube3 import YoutubeClient, upload
from youtube3.cli import upload_video

SESSION = "https://upload.example.invalid/synthetic-session"


@pytest.fixture
def video(tmp_path):
    path = tmp_path / "video.mp4"
    path.write_bytes(b"synthetic media" * 40000)
    return path


def prepared(responses):
    http = HttpMockSequence(responses)
    client = YoutubeClient(service=build("youtube", "v3", http=http, developerKey="test-key"))
    client._channel = {"id": "UCmine", "title": "Mine"}
    return client, http


def response(status=200, body=None, **headers):
    return ({"status": str(status), **headers}, json.dumps(body) if body is not None else "")


def test_dry_run_no_insert_request_and_private_default(video):
    client, http = prepared([])
    result = client.upload_video(video, title="An episode")
    assert result["applied"] is False and result["result"] is None
    assert result["plan"]["body"]["status"]["privacyStatus"] == "private"
    assert result["plan"]["channel_id"] == "UCmine"
    assert not http.request_sequence


def test_canned_resumable_chunks_progress_id_and_metadata(video):
    client, http = prepared([response(location=SESSION), response(308, range="bytes=0-262143"),
                             response(308, range="bytes=0-524287"), response(body={"id": "new-video"})])
    progress = []
    result = client.upload_video(video, title="Episode", description="Description", tags=["one", "two words"],
                                 privacy="unlisted", made_for_kids=False, chunk_size=upload.CHUNK_UNIT,
                                 apply=True, progress=lambda done, total: progress.append((done, total)))
    assert result["result"]["video_id"] == "new-video"
    assert result["result"]["uploaded_bytes"] == video.stat().st_size
    assert progress == [(262144, video.stat().st_size), (524288, video.stat().st_size)]
    requests = http.request_sequence
    assert [r[1] for r in requests] == ["POST", "PUT", "PUT", "PUT"]
    metadata = json.loads(requests[0][2])
    assert metadata["snippet"] == {"title": "Episode", "description": "Description", "categoryId": "22", "tags": ["one", "two words"]}
    assert metadata["status"] == {"privacyStatus": "unlisted", "selfDeclaredMadeForKids": False}
    assert all(r[0] == SESSION for r in requests[1:])
    assert SESSION not in json.dumps(result)


def test_transient_error_retries_same_session_not_insert(video, monkeypatch):
    monkeypatch.setattr(upload.time, "sleep", lambda _: None)
    client, http = prepared([response(location=SESSION), response(503, {"error": {"code": 503, "message": "Retry"}}),
                             response(308, range="bytes=0-0"), response(body={"id": "recovered"})])
    result = client.upload_video(video, title="Episode", retries=1, apply=True)
    assert result["result"]["video_id"] == "recovered"
    assert sum(r[1] == "POST" for r in http.request_sequence) == 1
    assert all(r[0] == SESSION for r in http.request_sequence[1:])


def test_exhausted_retries_have_unknown_outcome_without_session_disclosure(video, monkeypatch):
    monkeypatch.setattr(upload.time, "sleep", lambda _: None)
    failure = response(503, {"error": {"code": 503, "message": SESSION}})
    client, http = prepared([response(location=SESSION), failure, failure])
    with pytest.raises(upload.UploadError) as result:
        client.upload_video(video, title="Episode", retries=1, apply=True)
    assert result.value.outcome == "unknown"
    assert SESSION not in str(result.value)
    assert sum(r[1] == "POST" for r in http.request_sequence) == 1


def test_session_creation_failure_never_retried(video, monkeypatch):
    monkeypatch.setattr(upload.time, "sleep", lambda _: pytest.fail("must not retry session creation"))
    client, http = prepared([response(503, {"error": {"code": 503, "message": "Unavailable"}})])
    with pytest.raises(upload.UploadError, match="uncertain"):
        client.upload_video(video, title="Episode", retries=3, apply=True)
    assert len(http.request_sequence) == 1


def test_missing_id_never_reuploads(video):
    client, http = prepared([response(location=SESSION), response(body={"kind": "youtube#video"})])
    with pytest.raises(upload.UploadError, match="no video ID"):
        client.upload_video(video, title="Episode", apply=True)
    assert sum(r[1] == "POST" for r in http.request_sequence) == 1


def test_progress_interruption_stops_without_reinsert(video):
    client, http = prepared([response(location=SESSION), response(308, range="bytes=0-262143")])

    def interrupted(*_):
        raise KeyboardInterrupt

    with pytest.raises(upload.UploadError, match="interrupted"):
        client.upload_video(video, title="Episode", chunk_size=upload.CHUNK_UNIT, apply=True, progress=interrupted)
    assert len(http.request_sequence) == 2


@pytest.mark.parametrize("options", [{"title": ""}, {"privacy": "friends"}, {"retries": -1}, {"chunk_size": 1},
                                      {"tags": "wrong"}, {"category_id": "abc"}, {"description": "x" * 5001}])
def test_invalid_metadata_rejected_before_requests(video, options):
    client, http = prepared([])
    with pytest.raises(upload.UploadError) as result:
        client.upload_video(video, **{"title": "Episode", **options}, apply=True)
    assert result.value.outcome == "not_started"
    assert not http.request_sequence


def test_missing_unsupported_and_empty_input(tmp_path):
    for filename, content in [("missing.mp4", None), ("empty.mp4", b""), ("wrong.txt", b"data")]:
        path = tmp_path / filename
        if content is not None:
            path.write_bytes(content)
        with pytest.raises(upload.UploadError):
            upload.upload_spec(path, title="Episode")


def test_upload_cli_dry_run(video, monkeypatch, capsys):
    client, http = prepared([])
    monkeypatch.setattr(upload_video, "client", lambda args: client)
    monkeypatch.setattr(sys, "argv", ["upload", str(video), "--title", "Episode"])
    upload_video.main()
    assert "Dry run" in capsys.readouterr().out
    assert not http.request_sequence
