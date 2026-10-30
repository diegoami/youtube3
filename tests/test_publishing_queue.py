import json
import sys

import pytest
from googleapiclient.discovery import build
from googleapiclient.http import HttpMockSequence

from youtube3 import YoutubeClient, publishing_batch as batch, publishing_job as jobs, publishing_queue as queue
from youtube3.cli import publishing_batch as cli


def response(body=None, status=200, **headers):
    return ({"status": str(status), **headers}, json.dumps(body) if body is not None else "")


def resource(identity="v1", title="Episode"):
    return response({"items": [{"id": identity, "snippet": {"channelId": "UCmine", "title": title, "description": "", "categoryId": "22"},
                                "status": {"privacyStatus": "private", "embeddable": False}}]})


def prepared(*responses):
    http = HttpMockSequence(list(responses))
    client = YoutubeClient(service=build("youtube", "v3", http=http, developerKey="test-key"))
    client._channel = {"id": "UCmine"}
    return client, http


def uploads(identity="v1"):
    return [response(location="https://upload.example.invalid/synthetic"), response({"id": identity}), resource(identity)]


@pytest.fixture
def inputs(tmp_path):
    media = tmp_path / "one.mp4"
    media.write_bytes(b"synthetic media one")
    client, _ = prepared()
    job = jobs.plan_publishing_job(client, file=media, title="Episode")
    plan = {"schema": batch.PLAN_SCHEMA, "channel_id": "UCmine", "profile": None,
            "entries": [{"id": "one", "job": job, "playlists": []}]}
    return media, plan, tmp_path / "queue.json", tmp_path / "ledger.json"


def test_completed_queue_resume_never_reuploads(inputs):
    media, plan, path, ledger = inputs
    queue.initialize_queue(plan, path, ledger_path=ledger)
    client, http = prepared(*uploads())
    result = queue.run_queue(client, path)
    assert result["state"] == "completed"
    assert result["entries"]["one"]["video_id"] == "v1"
    assert sum(method == "POST" for uri, method, body, headers in http.request_sequence) == 1
    media.unlink()
    second, second_http = prepared()
    assert queue.run_queue(second, path, resume=True)["state"] == "completed"
    assert not second_http.request_sequence
    assert "upload.example" not in ledger.read_text(encoding="utf-8")


def test_pause_between_stages_and_resume_with_known_id(inputs, monkeypatch):
    media, plan, path, ledger = inputs
    queue.initialize_queue(plan, path, ledger_path=ledger)
    client, http = prepared(*uploads()[:2])
    original = queue._record

    def pause_after_upload(queue_state, ledger_state, identity, state, video_id=None):
        original(queue_state, ledger_state, identity, state, video_id)
        if state == "uploaded":
            queue.request_pause(path)

    monkeypatch.setattr(queue, "_record", pause_after_upload)
    result = queue.run_queue(client, path)
    assert result["state"] == "paused" and result["entries"]["one"]["video_id"] == "v1"
    assert len(http.request_sequence) == 2
    monkeypatch.setattr(queue, "_record", original)
    media.unlink()
    second, second_http = prepared(resource(), resource())
    assert queue.run_queue(second, path, resume=True)["state"] == "completed"
    assert all(method == "GET" for uri, method, body, headers in second_http.request_sequence)


def test_duplicate_content_in_batch_rejected_before_any_upload(inputs, tmp_path):
    media, plan, path, ledger = inputs
    other = tmp_path / "renamed.mp4"
    other.write_bytes(media.read_bytes())
    client, _ = prepared()
    plan["entries"].append({"id": "two", "job": jobs.plan_publishing_job(client, file=other, title="Other"), "playlists": []})
    with pytest.raises(queue.QueueError, match="duplicate video content"):
        queue.initialize_queue(plan, path, ledger_path=ledger)
    assert not path.exists() and not ledger.exists()


def test_per_channel_ledger_recognizes_renamed_file_without_metadata_changes(inputs, tmp_path):
    media, plan, path, ledger = inputs
    queue.initialize_queue(plan, path, ledger_path=ledger)
    first, _ = prepared(*uploads())
    queue.run_queue(first, path)
    other = tmp_path / "renamed.mp4"
    other.write_bytes(media.read_bytes())
    second, http = prepared()
    new_job = jobs.plan_publishing_job(second, file=other, title="Should not change existing title")
    plan["entries"][0]["job"] = new_job
    other_path = tmp_path / "other-queue.json"
    queue.initialize_queue(plan, other_path, ledger_path=ledger)
    result = queue.run_queue(second, other_path)
    assert result["entries"]["one"]["state"] == "duplicate"
    assert result["entries"]["one"]["video_id"] == "v1"
    assert not http.request_sequence


def test_uncertain_upload_blocks_all_reuploads_and_explicit_recovery_checks_owner(inputs):
    _, plan, path, ledger = inputs
    queue.initialize_queue(plan, path, ledger_path=ledger)
    first, http = prepared(response({"error": {"code": 503, "message": "Unavailable"}}, status=503))
    result = queue.run_queue(first, path)
    assert result["entries"]["one"]["state"] == "blocked"
    second, second_http = prepared()
    result = queue.run_queue(second, path, resume=True, retry=True)
    assert result["entries"]["one"]["state"] == "blocked" and not second_http.request_sequence
    recovery, _ = prepared(resource())
    queue.recover_entry(recovery, path, "one", video_id="v1")
    final, final_http = prepared(resource(), resource())
    assert queue.run_queue(final, path, resume=True)["state"] == "completed"
    assert all(method == "GET" for uri, method, body, headers in final_http.request_sequence)
    assert len(http.request_sequence) == 1


def test_queue_checkpoint_failure_after_upload_retains_known_id(inputs, monkeypatch):
    _, plan, path, ledger = inputs
    queue.initialize_queue(plan, path, ledger_path=ledger)
    original = queue._write

    def fail_queue_after_upload(document, destination, **kwargs):
        if str(destination) == str(path) and document["entries"]["one"]["video_id"]:
            raise OSError("disk full")
        return original(document, destination, **kwargs)

    monkeypatch.setattr(queue, "_write", fail_queue_after_upload)
    client, _ = prepared(*uploads()[:2])
    with pytest.raises(queue.QueueError) as result:
        queue.run_queue(client, path)
    assert result.value.queue["entries"]["one"]["video_id"] == "v1"
    monkeypatch.setattr(queue, "_write", original)
    second, http = prepared(resource(), resource())
    assert queue.run_queue(second, path, resume=True)["state"] == "completed"
    assert all(method == "GET" for uri, method, body, headers in http.request_sequence)


def test_changed_file_and_shared_writer_lock_prevent_upload(inputs):
    media, plan, path, ledger = inputs
    queue.initialize_queue(plan, path, ledger_path=ledger)
    client, http = prepared()
    with queue.locked(str(ledger) + ".lock"):
        with pytest.raises(queue.QueueError, match="Another"):
            queue.run_queue(client, path)
    media.write_bytes(b"changed")
    result = queue.run_queue(client, path)
    assert result["entries"]["one"]["state"] == "failed" and not http.request_sequence


def test_queue_cli_dry_run_never_creates_state_or_logs_in(inputs, tmp_path, monkeypatch, capsys):
    _, plan, path, ledger = inputs
    source = tmp_path / "plan.json"
    batch.save_plan(plan, source)
    monkeypatch.setattr(cli, "client", lambda _: pytest.fail("preview logged in"))
    monkeypatch.setattr(sys, "argv", ["publishing-batch", "run", str(source), "--queue", str(path), "--ledger", str(ledger)])
    cli.main()
    assert "Dry run" in capsys.readouterr().out
    assert not path.exists() and not ledger.exists()


def test_playlist_membership_precedes_publication_and_recovers_uncertain_insert(inputs):
    _, plan, path, ledger = inputs
    plan["entries"][0]["playlists"] = ["PLtest"]
    plan["entries"][0]["job"]["publication"]["privacy"] = "public"
    plan["entries"][0]["job"]["stages"]["publication"] = "pending"
    queue.initialize_queue(plan, path, ledger_path=ledger)
    owner = response({"items": [{"snippet": {"channelId": "UCmine"}}]})
    first, http = prepared(*uploads(), owner, response({"items": []}), response({"error": {"code": 500, "message": "Uncertain"}}, status=500))
    result = queue.run_queue(first, path)
    assert result["entries"]["one"]["state"] == "failed"
    assert result["entries"]["one"]["playlists"]["PLtest"] == "unknown"
    second, second_http = prepared(resource(), owner, response({"items": [{"id": "membership"}]}), resource(), resource(), response({}))
    result = queue.run_queue(second, path, resume=True, retry=True, stage="playlist")
    assert result["state"] == "completed"
    assert all(method != "POST" for uri, method, body, headers in second_http.request_sequence)
    assert sum(method == "PUT" and "/youtube/v3/videos?" in uri for uri, method, body, headers in second_http.request_sequence) == 1


def test_mixed_results_targeted_retry_skips_completed_entries(inputs, tmp_path):
    _, plan, path, ledger = inputs
    other = tmp_path / "two.mp4"
    other.write_bytes(b"different video")
    planner, _ = prepared()
    plan["entries"].append({"id": "two", "job": jobs.plan_publishing_job(planner, file=other, title="Episode"), "playlists": []})
    queue.initialize_queue(plan, path, ledger_path=ledger)
    failure = response({"error": {"code": 403, "message": "Refused"}}, status=403)
    first, _ = prepared(*uploads()[:2], resource(title="Old"), failure, *uploads("v2"))
    result = queue.run_queue(first, path, continue_on_error=True)
    assert result["entries"]["one"]["state"] == "failed"
    assert result["entries"]["two"]["state"] == "completed"
    second, http = prepared(resource(title="Old"), resource(title="Old"), response({}))
    complete = queue.run_queue(second, path, resume=True, retry=True, select=["one"], stage="metadata")
    assert complete["state"] == "completed"
    assert all(method != "POST" for uri, method, body, headers in http.request_sequence)
    assert sum(method == "PUT" for uri, method, body, headers in http.request_sequence) == 1


def test_real_subprocess_cannot_take_active_channel_lock(inputs):
    import subprocess
    _, _, _, ledger = inputs
    script = 'import sys; from youtube3.publishing_queue import locked, QueueError\ntry:\n with locked(sys.argv[1]): sys.exit(2)\nexcept QueueError: sys.exit(0)\n'
    with queue.locked(str(ledger) + ".lock"):
        result = subprocess.run([sys.executable, "-c", script, str(ledger) + ".lock"], capture_output=True, timeout=20)
    assert result.returncode == 0
    with queue.locked(str(ledger) + ".lock"):
        pass


def test_ledger_checkpoint_path_cannot_collide_with_job(inputs):
    _, plan, path, _ = inputs
    with pytest.raises(queue.QueueError, match="paths must differ"):
        queue.initialize_queue(plan, path, ledger_path=str(path) + ".jobs/one.json")
    assert not path.exists()


def test_missing_job_with_reserved_intent_cannot_restart_upload(inputs):
    _, plan, path, ledger = inputs
    initialized = queue.initialize_queue(plan, path, ledger_path=ledger)
    queue._record(initialized, queue._ledger(initialized), "one", "reserved")
    client, http = prepared()
    result = queue.run_queue(client, path, resume=True, retry=True)
    assert result["state"] == "blocked" and not http.request_sequence


def test_explicit_no_upload_confirmation_allows_new_attempt(inputs):
    _, plan, path, ledger = inputs
    initialized = queue.initialize_queue(plan, path, ledger_path=ledger)
    queue._record(initialized, queue._ledger(initialized), "one", "unknown")
    client, http = prepared()
    queue.recover_entry(client, path, "one", confirm_not_uploaded=True)
    assert not http.request_sequence
    next_client, _ = prepared(*uploads())
    assert queue.run_queue(next_client, path, resume=True)["state"] == "completed"
    with pytest.raises(queue.QueueError, match="known upload"):
        queue.recover_entry(next_client, path, "one", confirm_not_uploaded=True)


def test_concurrent_pause_requests_both_succeed(inputs, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from pathlib import Path
    from threading import Barrier

    _, plan, path, ledger = inputs
    queue.initialize_queue(plan, path, ledger_path=ledger)
    flag = Path(str(path.resolve()) + ".pause")
    original = queue.artwork.save_bytes
    ready = Barrier(2)

    def simultaneous_create(destination, data, **kwargs):
        if Path(destination) == flag:
            # Both callers reach exclusive creation before either creates it.
            ready.wait(timeout=10)
        return original(destination, data, **kwargs)

    monkeypatch.setattr(queue.artwork, "save_bytes", simultaneous_create)
    with ThreadPoolExecutor(max_workers=2) as workers:
        requests = [workers.submit(queue.request_pause, path) for _ in range(2)]
        for request in requests:
            assert request.result(timeout=15) is None
    assert flag.read_bytes() == b"pause\n"


def test_pause_cli_succeeds_if_another_caller_creates_flag_first(inputs, monkeypatch, capsys):
    from pathlib import Path

    _, plan, path, ledger = inputs
    queue.initialize_queue(plan, path, ledger_path=ledger)
    flag = Path(str(path.resolve()) + ".pause")
    original = queue.artwork.save_bytes

    def another_caller_wins(destination, data, **kwargs):
        if Path(destination) == flag:
            original(flag, b"existing pause request\n")
        return original(destination, data, **kwargs)

    monkeypatch.setattr(queue.artwork, "save_bytes", another_caller_wins)
    monkeypatch.setattr(cli, "client", lambda _: pytest.fail("pause must not log in"))
    monkeypatch.setattr(sys, "argv", ["publishing-batch", "pause", str(path)])
    cli.main()
    assert "Pause requested" in capsys.readouterr().out
    assert flag.read_bytes() == b"existing pause request\n"


def test_pause_reports_other_file_errors(inputs, monkeypatch):
    _, plan, path, ledger = inputs
    queue.initialize_queue(plan, path, ledger_path=ledger)

    def refused(*args, **kwargs):
        raise PermissionError("synthetic permission failure")

    monkeypatch.setattr(queue.artwork, "save_bytes", refused)
    with pytest.raises(PermissionError, match="synthetic permission failure"):
        queue.request_pause(path)
