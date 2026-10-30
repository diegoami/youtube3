import json
import sys

import pytest

from youtube3 import publishing_batch as batch
from youtube3.cli import publishing_batch as cli


@pytest.fixture
def configuration(tmp_path):
    for name in ("one", "two"):
        (tmp_path / f"{name}.mp4").write_bytes(name.encode())
    path = tmp_path / "batch.json"
    path.write_text(json.dumps({"schema": batch.BATCH_SCHEMA, "settings": {"title_template": "Episode {episode:03d}"},
        "schedule": {"start": "2099-01-01T18:00:00+01:00", "interval_minutes": 1440},
        "entries": [{"id": "one", "file": "one.mp4"}, {"id": "two", "file": "two.mp4", "episode": 9}]}), encoding="utf-8")
    return path


def client(fake):
    f = fake()
    f.client._channel = {"id": "UCmine", "title": "Mine"}
    return f


def test_batch_fixed_mapping_cadence_and_saved_plan(configuration, fake, tmp_path):
    f = client(fake)
    entries = batch.resolve_batch(configuration)
    assert [entry["settings"]["title"] for entry in entries] == ["Episode 001", "Episode 009"]
    assert [entry["settings"]["publish_at"] for entry in entries] == ["2099-01-01T17:00:00Z", "2099-01-02T17:00:00Z"]
    plan = batch.plan_batch(f.client, entries)
    assert not f.requests
    destination = tmp_path / "plan.json"
    batch.save_plan(plan, destination)
    configuration.unlink()
    assert batch.load_plan(destination) == plan
    assert plan["entries"][1]["job"]["upload"]["file"]["path"].endswith("two.mp4")


@pytest.mark.parametrize("problem", ["duplicate_id", "duplicate_source", "naive_time", "invalid_interval", "unknown"])
def test_batch_invalid_input_rejected(configuration, problem):
    document = json.loads(configuration.read_text(encoding="utf-8"))
    if problem == "duplicate_id":
        document["entries"][1]["id"] = "one"
    elif problem == "duplicate_source":
        document["entries"][1]["file"] = "one.mp4"
    elif problem == "naive_time":
        document["schedule"]["start"] = "2099-01-01T18:00:00"
    elif problem == "invalid_interval":
        document["schedule"]["interval_minutes"] = 0
    else:
        document["apply"] = True
    configuration.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError):
        batch.resolve_batch(configuration)


def test_playlist_preflight_and_idempotent_membership(fake):
    owner = {"items": [{"snippet": {"channelId": "UCmine"}}]}
    f = fake(owner, {"items": []}, {"id": "membership"}, owner, {"items": [{"id": "membership"}]})
    f.client._channel = {"id": "UCmine"}
    assert batch.ensure_playlist_member(f.client, "PLtest", "v1")["state"] == "added"
    assert batch.ensure_playlist_member(f.client, "PLtest", "v1")["state"] == "present"
    writes = [r for r in f.requests if r.method != "GET"]
    assert len(writes) == 1
    assert writes[0].body == {"snippet": {"playlistId": "PLtest", "resourceId": {"kind": "youtube#video", "videoId": "v1"}}}
    assert f.requests[1].params["videoId"] == "v1"


def test_uncertain_playlist_recovery_reads_without_inserting(fake):
    f = fake({"items": [{"snippet": {"channelId": "UCmine"}}]}, {"items": []})
    f.client._channel = {"id": "UCmine"}
    assert batch.ensure_playlist_member(f.client, "PLtest", "v1", allow_insert=False)["state"] == "unknown"
    assert all(r.method == "GET" for r in f.requests)


def test_batch_cli_preview_no_files_or_account_writes(configuration, fake, monkeypatch, capsys):
    f = client(fake)
    monkeypatch.setattr(cli, "client", lambda args: f.client)
    monkeypatch.setattr(sys, "argv", ["publishing-batch", "plan", str(configuration)])
    before = set(configuration.parent.iterdir())
    cli.main()
    assert "Preview" in capsys.readouterr().out
    assert set(configuration.parent.iterdir()) == before and not f.requests


def test_per_video_configuration_overrides_batch_defaults(configuration, tmp_path):
    video = tmp_path / "video.json"
    video.write_text(json.dumps({"schema": "youtube3.publishing-video.v1", "file": "one.mp4", "episode": 19,
        "settings": {"title": "Per-video", "publish_at": "2099-03-01T00:00:00Z"}}), encoding="utf-8")
    document = json.loads(configuration.read_text(encoding="utf-8"))
    document["entries"] = [{"id": "one", "config": "video.json"}]
    configuration.write_text(json.dumps(document), encoding="utf-8")
    row = batch.resolve_batch(configuration)[0]
    assert row["settings"]["title"] == "Per-video"
    assert row["settings"]["publish_at"] == "2099-03-01T00:00:00Z"
