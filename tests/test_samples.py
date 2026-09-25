"""The samples' own logic, with the login replaced: found missing when a sample
called a function that did not exist and only the live run noticed."""

import argparse
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "samples"))
import import_history  # noqa: E402
from test_history import takeout_zip  # noqa: E402


class FakeClient:
    def __init__(self, liked):
        self.liked = liked

    def iterate_liked_videos(self):
        return iter([{"video_id": video_id, "available": True} for video_id in self.liked])


def run(tmp_path, monkeypatch, liked, capsys):
    monkeypatch.setattr(import_history, "client", lambda args: FakeClient(liked))
    args = argparse.Namespace(
        takeout=takeout_zip(tmp_path / "t.zip"), out=tmp_path / "h.json", include_ads=False,
        include_music=False, profile="me",
    )
    summary, found_likes = import_history.import_and_check(args)
    return summary, found_likes, capsys.readouterr().out


def test_a_profile_whose_likes_are_watched_gets_no_warning(tmp_path, monkeypatch, capsys):
    liked = ["aaa", "bbb", "ccc", "ddd"]
    _, found, out = run(tmp_path, monkeypatch, liked, capsys)

    assert found == set(liked)
    assert "4 of the channel's 4 likes are among these watches." in out
    assert "Warning" not in out


def test_a_profile_whose_likes_are_not_watched_is_warned(tmp_path, monkeypatch, capsys):
    liked = [f"elsewhere{i}" for i in range(60)]
    _, _, out = run(tmp_path, monkeypatch, liked, capsys)

    assert "0 of the channel's 60 likes" in out
    assert "looks like another account's history" in out


def test_no_export_found_is_a_clear_error(tmp_path, monkeypatch):
    monkeypatch.setattr(import_history.history, "find_latest_takeout", lambda: None)
    args = argparse.Namespace(takeout=None, out=tmp_path / "h.json", include_ads=False, include_music=False, profile=None)

    with pytest.raises(SystemExit, match="no takeout"):
        import_history.import_and_check(args)
