import os
import sys

import pytest

from youtube3.cli import main
from youtube3.cli.common import default_path
from youtube3.cli.subscribe_channel import subscribe


def test_cli_help_lists_installed_commands(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["youtube3", "--help"])

    main.main()

    output = capsys.readouterr().out
    assert "profiles" in output
    assert "likes" in output
    assert "playlist" in output


def test_setup_copies_secrets_to_private_config_path(tmp_path, monkeypatch, capsys):
    source = tmp_path / "client.json"
    source.write_text('{"installed": {"client_id": "fake"}}', encoding="utf-8")
    config = tmp_path / "config" / "profiles"
    monkeypatch.setattr(main.profiles, "config_dir", lambda: config)

    main._setup([str(source)])

    destination = config.parent / "client_secrets.json"
    assert destination.read_text(encoding="utf-8") == source.read_text(encoding="utf-8")
    if os.name != "nt":
        assert destination.stat().st_mode & 0o777 == 0o600
    assert str(destination) in capsys.readouterr().out


def test_setup_requires_one_source_path():
    with pytest.raises(SystemExit, match="usage: youtube3 setup"):
        main._setup([])


@pytest.mark.parametrize(
    ("argv", "module"),
    [
        (["youtube3", "profiles", "list"], "youtube3.cli.profiles"),
        (["youtube3", "likes", "export"], "youtube3.cli.export_liked_videos"),
        (["youtube3", "publish"], "youtube3.cli.publish_video"),
        (["youtube3", "playlist", "show"], "youtube3.cli.show_files_in_playlist"),
        (["youtube3", "video", "check"], "youtube3.cli.verify_video"),
        (["youtube3", "channel", "videos"], "youtube3.cli.channel_videos"),
        (["youtube3", "subscriptions", "list"], "youtube3.cli.show_subscribed"),
    ],
)
def test_cli_dispatches_commands(monkeypatch, argv, module):
    called = []
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr(main.runpy, "run_module", lambda name, run_name: called.append((name, run_name)))

    main.main()

    assert called == [(module, "__main__")]


def test_channel_videos_prints_each_video_and_writes_the_export(tmp_path, monkeypatch, capsys):
    class FakeClient:
        def iterate_channel_videos(self):
            return [
                {
                    "video_id": "v1",
                    "title": "First",
                    "published_at": "2024-01-02T00:00:00Z",
                    "privacy": "public",
                    "views": 12,
                    "duration": "PT4M13S",
                }
            ]

    export = tmp_path / "channel.json"
    monkeypatch.setattr(sys, "argv", ["youtube3", "channel", "videos", "--out", str(export)])
    monkeypatch.setattr("youtube3.cli.common.client", lambda args: FakeClient())

    main.main()

    output = capsys.readouterr().out
    assert "v1" in output
    assert "First" in output
    assert f"1 videos saved to {export}" in output
    assert export.exists()


def test_subscribe_is_dry_run_without_apply():
    class FakeClient:
        def subscribe_channel(self, channel_id):
            raise AssertionError("dry run must not write")

    assert "Dry run" in subscribe(FakeClient(), "channel", False)


def test_invalid_profile_default_output_is_a_cli_error():
    with pytest.raises(SystemExit, match="^Error:.*profile"):
        default_path(None, "channel", ".json", "Diego")
