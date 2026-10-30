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
