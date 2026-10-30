import json
import sys

import pytest

from youtube3 import publishing_config as config
from youtube3.cli import publish_job


@pytest.fixture
def presets(tmp_path):
    path = tmp_path / "presets.json"
    path.write_text(json.dumps({"schema": config.SCHEMA, "defaults": {"privacy": "private", "tags": ["default"],
        "description": "Literal {braces}", "variables": {"series": "My series"}}, "presets": {"series": {
        "profile": "mybrand", "expected_channel_id": "UCmine", "title_template": "{series} — {episode:03d}",
        "thumbnail_template": "artwork/{stem}.png", "made_for_kids": False}}}), encoding="utf-8")
    return path


def test_preset_templates_paths_false_values_and_overrides(presets):
    settings = config.resolve_preset(presets, "series", context={"episode": 7, "stem": "episode7"})
    assert settings["title"] == "My series — 007"
    assert settings["description"] == "Literal {braces}"
    assert settings["thumbnail"] == str(presets.parent / "artwork" / "episode7.png")
    assert settings["privacy"] == "private" and settings["made_for_kids"] is False
    overridden = config.resolve_preset(presets, "series", overrides={"title": "Explicit", "tags": []}, context={"stem": "ep"})
    assert overridden["title"] == "Explicit" and overridden["tags"] == []


@pytest.mark.parametrize("settings", [{"apply": True}, {"credentials": {}}, {"made_for_kids": "false"},
                                       {"tags": "a,b"}, {"retries": True}, {"variables": {"a": {}}}])
def test_invalid_settings_rejected(settings):
    with pytest.raises(config.ConfigurationError):
        config.resolve_settings(settings)


@pytest.mark.parametrize("template", ["{missing}", "{obj.__class__}", "{obj[x]}", "{episode:99999d}", "{episode!r}"])
def test_unsafe_or_missing_template_variables_rejected(template):
    with pytest.raises(config.ConfigurationError):
        config.resolve_settings({"title_template": template}, context={"episode": 1, "obj": "test"})


def test_duplicate_json_and_yaml_keys_rejected(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"a": 1, "a": 2}', encoding="utf-8")
    with pytest.raises(config.ConfigurationError, match="Duplicate"):
        config.read_document(path)
    path = tmp_path / "settings.yaml"
    path.write_text('privacy: private\nprivacy: public\n', encoding="utf-8")
    with pytest.raises(config.ConfigurationError, match="Duplicate"):
        config.read_document(path)


def test_expected_channel_mismatch_is_rejected():
    class Client:
        def signed_in_channel(self):
            return {"id": "UCother"}
    with pytest.raises(config.ConfigurationError, match="expected channel"):
        config.check_destination(Client(), {"expected_channel_id": "UCmine"})


def test_preset_cli_preview_uses_profile_and_never_writes(presets, tmp_path, monkeypatch, capsys):
    media = tmp_path / "episode.mp4"
    media.write_bytes(b"synthetic")
    # Omit the image for this CLI test so it requires no real artwork/API reads.
    document = json.loads(presets.read_text(encoding="utf-8"))
    document["presets"]["series"].pop("thumbnail_template")
    presets.write_text(json.dumps(document), encoding="utf-8")

    class Client:
        profile = "mybrand"
        def signed_in_channel(self):
            return {"id": "UCmine"}

    def selected(args):
        assert args.profile == "mybrand"
        return Client()

    monkeypatch.setattr(publish_job, "client", selected)
    monkeypatch.setattr(sys, "argv", ["publishing", "--file", str(media), "--presets", str(presets), "--preset", "series", "--episode", "7"])
    publish_job.main()
    output = capsys.readouterr().out
    assert "Dry run" in output and "007" in output


def test_per_video_precedence_false_empty_clear_and_origins(presets, tmp_path):
    folder = tmp_path / "videos"
    folder.mkdir()
    path = folder / "video.json"
    path.write_text(json.dumps({"schema": config.VIDEO_SCHEMA, "file": "episode.mp4", "presets": "../presets.json",
        "preset": "series", "episode": 9, "settings": {"title": "Video title", "tags": [], "thumbnail": "local.png", "made_for_kids": False}}), encoding="utf-8")
    result = config.resolve_video_config(path, overrides={"title": "CLI title", "privacy": None})
    assert result["file"] == str(folder / "episode.mp4")
    settings = result["settings"]
    assert settings["title"] == "CLI title" and settings["tags"] == []
    assert settings["made_for_kids"] is False and settings["privacy"] is None
    assert settings["thumbnail"] == str(folder / "local.png")
    assert settings["description"] == "Literal {braces}"


def test_per_video_yaml_multiline_and_null(tmp_path):
    path = tmp_path / "video.yaml"
    path.write_text('schema: youtube3.publishing-video.v1\nfile: episode.mp4\nsettings:\n  title: Episode\n  description: |\n    Line one\n    Line two\n  tags: []\n  made_for_kids: false\n  privacy: null\n', encoding="utf-8")
    result = config.resolve_video_config(path)
    assert result["settings"]["description"] == "Line one\nLine two\n"
    assert result["settings"]["made_for_kids"] is False
    assert result["settings"]["privacy"] is None


def test_configuration_cannot_enable_apply_and_fails_before_login(tmp_path, monkeypatch):
    path = tmp_path / "video.json"
    path.write_text(json.dumps({"schema": config.VIDEO_SCHEMA, "file": "episode.mp4", "apply": True}), encoding="utf-8")
    monkeypatch.setattr(publish_job, "client", lambda _: pytest.fail("invalid config logged in"))
    monkeypatch.setattr(sys, "argv", ["publishing", "--config", str(path)])
    with pytest.raises(SystemExit) as result:
        publish_job.main()
    assert result.value.code == 1


def test_config_cli_preview_and_unset(tmp_path, monkeypatch, capsys):
    path = tmp_path / "video.json"
    (tmp_path / "episode.mp4").write_bytes(b"synthetic")
    path.write_text(json.dumps({"schema": config.VIDEO_SCHEMA, "file": "episode.mp4", "settings": {
        "title": "Episode", "tags": ["default"], "privacy": "public"}}), encoding="utf-8")

    class Client:
        profile = None
        def signed_in_channel(self):
            return {"id": "UCmine"}

    monkeypatch.setattr(publish_job, "client", lambda _: Client())
    monkeypatch.setattr(sys, "argv", ["publishing", "--config", str(path), "--unset", "privacy", "--tags", ""])
    publish_job.main()
    output = capsys.readouterr().out
    assert "Dry run" in output and '"privacyStatus": "private"' in output
    job = json.loads(output.split("\nDry run:")[0])
    assert job["publication"]["privacy"] is None
    assert job["metadata"]["tags"] == [] and "tags" not in job["upload"]["body"]["snippet"]
    assert not (tmp_path / "job.json").exists()


def test_per_video_home_relative_source_expands_before_config_directory(tmp_path):
    from pathlib import Path
    path = tmp_path / "video.json"
    path.write_text(json.dumps({"schema": config.VIDEO_SCHEMA, "file": "~/synthetic-publishing-video.mp4",
        "settings": {"title": "Episode"}}), encoding="utf-8")
    result = config.resolve_video_config(path)
    assert result["file"] == str(Path("~/synthetic-publishing-video.mp4").expanduser().resolve())
