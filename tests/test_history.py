import json
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from youtube3 import history

NOW = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)
SAMPLES = Path(__file__).parent.parent / "samples"


def watch(video_id, when, title=None, channel=("UC1", "Channel One"), **extra):
    entry = {
        "header": "YouTube",
        "title": f"Watched {title or 'title ' + video_id}",
        "titleUrl": f"https://www.youtube.com/watch?v={video_id}",
        "time": when,
        "products": ["YouTube"],
        "activityControls": ["YouTube watch history"],
    }
    if channel:
        entry["subtitles"] = [{"name": channel[1], "url": f"https://www.youtube.com/channel/{channel[0]}"}]
    entry.update(extra)
    return entry


WATCHES = [
    watch("aaa", "2026-09-20T10:00:00.123Z", title="Song A"),
    watch("bbb", "2026-09-21T09:00:00.000Z", channel=("UC2", "Other")),
    watch("aaa", "2026-09-22T08:00:00.000Z", title="Song A"),  # a rewatch
    {"header": "YouTube", "title": "Watched a video that has been removed", "time": "2026-09-19T00:00:00Z"},
    {"header": "YouTube", "title": "Ein Video, das entfernt wurde, angesehen", "time": "2026-09-18T00:00:00Z"},
    watch("adv", "2026-09-17T00:00:00Z", details=[{"name": "From Google Ads"}]),
    {**watch("mus", "2026-09-16T00:00:00Z"), "header": "YouTube Music"},
    watch("nochan", "2026-09-15T00:00:00Z", channel=None),
    {**watch("ccc", "2026-09-14T00:00:00Z"), "title": "„Lied C“ angesehen"},
    {"header": "YouTube", "title": "Viewed a post", "titleUrl": "https://www.youtube.com/post/xyz", "time": "2026-09-13T00:00:00Z"},
    watch("ddd", "2026-09-12T00:00:00Z", titleUrl="https://www.youtube.com/watch?v=ddd&t=30s&list=PL1"),
]
SEARCHES = [
    {"header": "YouTube", "title": "Searched for music", "titleUrl": "https://www.youtube.com/results?search_query=music", "time": "2026-09-20T00:00:00Z"}
]


def takeout_zip(path, watches=WATCHES, bom=True):
    body = json.dumps(watches, ensure_ascii=False).encode("utf-8")
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Takeout/YouTube und YouTube Music/Verlauf/Suchverlauf.json", json.dumps(SEARCHES))
        archive.writestr("Takeout/YouTube und YouTube Music/Verlauf/Wiedergabeverlauf.json", (b"\xef\xbb\xbf" if bom else b"") + body)
        archive.writestr("Takeout/archive_browser.html", "<html>index</html>")
    return path


# Finding the history


def test_the_watch_history_is_found_by_its_contents_under_any_name(tmp_path):
    entries = history.find_watch_history(takeout_zip(tmp_path / "takeout-1.zip"))

    assert len(entries) == len(WATCHES)


def test_an_unpacked_folder_works_too(tmp_path):
    with zipfile.ZipFile(takeout_zip(tmp_path / "t.zip")) as archive:
        archive.extractall(tmp_path / "unpacked")

    assert len(history.find_watch_history(tmp_path / "unpacked")) == len(WATCHES)


def test_a_history_exported_as_html_is_refused_with_how_to_fix_it(tmp_path):
    path = tmp_path / "t.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Takeout/YouTube/history/watch-history.html", '<a href="https://www.youtube.com/watch?v=aaa">x</a>')

    with pytest.raises(history.HistoryError, match="JSON"):
        history.find_watch_history(path)


def test_an_export_without_a_history_is_refused(tmp_path):
    path = tmp_path / "t.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Takeout/YouTube/history/search-history.json", json.dumps(SEARCHES))

    with pytest.raises(history.HistoryError, match="no watch history"):
        history.find_watch_history(path)


def test_something_else_is_refused(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("hello")

    with pytest.raises(history.HistoryError):
        history.find_watch_history(path)


# Records


def test_a_watch_becomes_a_record():
    assert history.history_record(WATCHES[0]) == {
        "video_id": "aaa",
        "title": "Song A",
        "channel_id": "UC1",
        "channel_title": "Channel One",
        "watched_at": "2026-09-20T10:00:00.123Z",
        "removed": False,
        "ad": False,
        "music": False,
    }


def test_a_removed_video_is_kept_in_any_language():
    english, german = history.history_record(WATCHES[3]), history.history_record(WATCHES[4])

    assert english["removed"] and german["removed"]
    assert english["video_id"] is None and german["title"] == "Ein Video, das entfernt wurde, angesehen"


def test_ads_and_music_are_marked():
    assert history.history_record(WATCHES[5])["ad"] is True
    assert history.history_record(WATCHES[6])["music"] is True


def test_a_video_whose_channel_is_gone_has_no_channel():
    record = history.history_record(WATCHES[7])

    assert (record["video_id"], record["channel_id"], record["channel_title"]) == ("nochan", None, None)


def test_only_the_english_prefix_is_removed_from_a_title():
    assert history.history_record(WATCHES[8])["title"] == "„Lied C“ angesehen"


def test_a_link_that_is_not_a_video_is_not_a_watch():
    assert history.history_record(WATCHES[9]) is None


def test_the_video_id_is_read_among_other_parameters():
    assert history.history_record(WATCHES[10])["video_id"] == "ddd"


# Import


def test_the_import_writes_the_history_newest_first_without_ads_or_music(tmp_path):
    out = tmp_path / "history.json"

    summary = history.import_history(takeout_zip(tmp_path / "t.zip"), out, now=NOW)

    saved = json.loads(out.read_text(encoding="utf-8"))
    ids = [v["video_id"] for v in saved["videos"]]
    assert ids == ["aaa", "bbb", "aaa", None, None, "nochan", "ccc", "ddd"]
    times = [v["watched_at"] for v in saved["videos"]]
    assert times == sorted(times, reverse=True) and times[0] == "2026-09-22T08:00:00.000Z"
    assert "adv" not in ids and "mus" not in ids
    assert saved["imported_at"] == "2026-09-24T12:00:00+00:00"
    assert summary["count"] == 8
    assert summary["videos"] == 5
    assert summary["rewatched"] == 1
    assert summary["removed"] == 2
    assert (summary["first"], summary["last"]) == ("2026-09-12T00:00:00Z", "2026-09-22T08:00:00.000Z")
    assert summary["left_out"] == {"ads": 1, "music": 1}
    # aaa twice, ccc and ddd: bbb is on the other channel, nochan on none.
    assert summary["top_channels"] == [
        {"id": "UC1", "title": "Channel One", "count": 4},
        {"id": "UC2", "title": "Other", "count": 1},
    ]


def test_ads_and_music_can_be_kept(tmp_path):
    summary = history.import_history(
        takeout_zip(tmp_path / "t.zip"), tmp_path / "h.json", include_ads=True, include_music=True, now=NOW
    )

    assert summary["count"] == 10
    assert summary["left_out"] == {"ads": 0, "music": 0}


def test_a_file_without_a_byte_order_mark_works(tmp_path):
    summary = history.import_history(takeout_zip(tmp_path / "t.zip", bom=False), tmp_path / "h.json", now=NOW)

    assert summary["count"] == 8


def test_the_import_logs_no_title_or_url(tmp_path, caplog):
    with caplog.at_level("DEBUG"):
        history.import_history(takeout_zip(tmp_path / "t.zip"), tmp_path / "h.json", now=NOW)

    assert "Song A" not in caplog.text and "youtube.com" not in caplog.text


def test_the_sample_prints_counts_only(tmp_path):
    source = takeout_zip(tmp_path / "t.zip")

    result = subprocess.run(
        [sys.executable, str(SAMPLES / "import_history.py"), "--takeout", str(source), "--out", str(tmp_path / "h.json")],
        capture_output=True,
        text=True,
        check=True,
    )

    assert "Watches: 8 of 5 different videos" in result.stdout
    for private in ("Song A", "Channel One", "youtube.com", "aaa"):
        assert private not in result.stdout


def test_the_sample_explains_an_html_export(tmp_path):
    path = tmp_path / "t.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Takeout/x/watch-history.html", '<a href="https://www.youtube.com/watch?v=aaa">x</a>')

    result = subprocess.run(
        [sys.executable, str(SAMPLES / "import_history.py"), "--takeout", str(path), "--out", str(tmp_path / "h.json")],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1 and "History set to JSON" in result.stderr


# The shape the owner's real export has for a video deleted or made private since (#51)


def unavailable(video_id, when, prefix="Watched "):
    url = f"https://www.youtube.com/watch?v={video_id}"
    return {"header": "YouTube", "title": prefix + url, "titleUrl": url, "time": when, "products": ["YouTube"]}


def test_a_video_whose_title_is_its_own_link_and_has_no_channel_is_unavailable():
    record = history.history_record(unavailable("gone1", "2026-09-10T00:00:00Z"))

    assert record["removed"] is True
    assert record["video_id"] == "gone1"
    assert record["title"] is None
    assert record["channel_id"] is None


def test_it_is_recognised_whatever_the_language_around_the_link():
    record = history.history_record(unavailable("gone2", "2026-09-10T00:00:00Z", prefix="Angesehen: "))

    assert record["removed"] is True and record["title"] is None


def test_a_real_title_that_mentions_a_link_is_not_unavailable():
    entry = watch("real", "2026-09-10T00:00:00Z", title="Tutorial: https://www.youtube.com/watch?v=real")

    assert history.history_record(entry)["removed"] is False


def test_the_import_counts_unavailable_videos_as_removed(tmp_path):
    source = takeout_zip(tmp_path / "t.zip", watches=[*WATCHES, unavailable("gone1", "2026-09-11T00:00:00Z")])

    summary = history.import_history(source, tmp_path / "h.json", now=NOW)

    assert summary["removed"] == 3
    assert summary["count"] == 9


def test_unavailable_videos_are_never_selected_for_an_action(tmp_path):
    records = [history.history_record(unavailable("gone1", "2026-09-11T00:00:00Z")), history.history_record(WATCHES[0])]

    assert [v["video_id"] for v in history.watched_videos(records)] == ["aaa"]


def test_a_title_that_is_exactly_its_link_is_unavailable():
    record = history.history_record(unavailable("gone3", "2026-09-10T00:00:00Z", prefix=""))

    assert record["removed"] is True and record["title"] is None


def test_a_long_real_title_with_a_link_is_not_unavailable_even_without_a_channel():
    url = "https://www.youtube.com/watch?v=real2"
    entry = {"header": "YouTube", "title": f"Watched Full lecture notes and slides are at {url} (part 2 of 7)", "titleUrl": url, "time": "2026-09-10T00:00:00Z"}

    assert history.history_record(entry)["removed"] is False
