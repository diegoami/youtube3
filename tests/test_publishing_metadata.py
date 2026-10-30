import json
import sys

import pytest

from youtube3 import publish, publishing_job, publishing_metadata, upload
from youtube3.cli import upload_video


def test_insert_options_keep_false_values_and_languages(fake, tmp_path):
    path = tmp_path / "episode.mp4"
    path.write_bytes(b"synthetic")
    f = fake()
    f.client._channel = {"id": "UCmine", "title": "Mine"}
    result = f.client.upload_video(path, title="Episode", made_for_kids=False, notify_subscribers=False,
        default_language="en-US", default_audio_language="de", license="creativeCommon", embeddable=False,
        public_stats_viewable=False, contains_synthetic_media=False)
    body = result["plan"]["body"]
    assert body["snippet"]["defaultLanguage"] == "en-US"
    assert body["snippet"]["defaultAudioLanguage"] == "de"
    assert body["status"] == {"privacyStatus": "private", "selfDeclaredMadeForKids": False,
        "license": "creativeCommon", "embeddable": False, "publicStatsViewable": False, "containsSyntheticMedia": False}
    upload._validate_plan(f.client, result["plan"])
    assert not f.requests


def test_update_preserves_unrelated_fields_and_controls_false(fake):
    resource = {"items": [{"id": "v1", "snippet": {"title": "Episode", "categoryId": "22", "tags": ["keep"],
        "defaultLanguage": "en"}, "status": {"privacyStatus": "private", "license": "youtube", "embeddable": True,
        "selfDeclaredMadeForKids": True, "publicStatsViewable": True, "containsSyntheticMedia": True}}]}
    f = fake(resource, {})
    plan = publish.plan_publish(f.client, "v1", default_audio_language="de", made_for_kids=False,
                                public_stats_viewable=False, contains_synthetic_media=False)
    publish.apply_publish(f.client, plan)
    body = f.requests[-1].body
    assert body["snippet"] == {"title": "Episode", "categoryId": "22", "tags": ["keep"], "defaultLanguage": "en", "defaultAudioLanguage": "de"}
    assert body["status"] == {"privacyStatus": "private", "license": "youtube", "embeddable": True,
        "selfDeclaredMadeForKids": False, "publicStatsViewable": False, "containsSyntheticMedia": False}


@pytest.mark.parametrize("options", [{"license": "invalid"}, {"embeddable": "false"}, {"default_language": "not a language"},
                                      {"contains_synthetic_media": 0}, {"category_id": 22}])
def test_invalid_metadata_fails_before_requests(fake, options):
    f = fake()
    with pytest.raises(ValueError):
        publish.plan_publish(f.client, "v1", **options)
    assert not f.requests


def test_old_checkpoint_and_new_optional_metadata_are_compatible(fake, tmp_path):
    path = tmp_path / "episode.mp4"
    path.write_bytes(b"synthetic")
    f = fake()
    f.client._channel = {"id": "UCmine"}
    old = publishing_job.plan_publishing_job(f.client, file=path, title="Episode")
    assert set(old["metadata"]) == {"title", "description", "tags"}
    assert publishing_job.validate_job(json.loads(json.dumps(old))) == old
    new = publishing_job.plan_publishing_job(f.client, file=path, title="Episode", embeddable=False, made_for_kids=False,
                                             default_language="en", notify_subscribers=True)
    assert new["metadata"]["embeddable"] is False
    assert new["upload"]["notify_subscribers"] is True
    assert publishing_job.validate_job(json.loads(json.dumps(new))) == new


def test_upload_cli_explicit_negative_booleans(fake, tmp_path, monkeypatch, capsys):
    path = tmp_path / "episode.mp4"
    path.write_bytes(b"synthetic")
    f = fake()
    f.client._channel = {"id": "UCmine"}
    monkeypatch.setattr(upload_video, "client", lambda _: f.client)
    monkeypatch.setattr(sys, "argv", ["upload", str(path), "--title", "Episode", "--no-made-for-kids", "--no-embeddable",
        "--no-public-stats-viewable", "--no-contains-synthetic-media", "--no-notify-subscribers"])
    upload_video.main()
    text = capsys.readouterr().out
    plan = json.loads(text.split("\nDry run:")[0])
    assert plan["body"]["status"]["selfDeclaredMadeForKids"] is False
    assert plan["body"]["status"]["embeddable"] is False
    assert plan["notify_subscribers"] is False
    assert not f.requests


def test_named_metadata_only():
    with pytest.raises(ValueError, match="Unknown"):
        publishing_metadata.parts({"arbitrary_api_field": True})
