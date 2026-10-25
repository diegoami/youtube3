"""Exercise real yt-dlp with local extractors and fake media transport only."""

from pathlib import Path

import pytest

from youtube3 import download


PLAYLIST = "PL0123456789abcdef"
VIDEO_IDS = ["BaW_jenozKc", "abcdefghijk", "lmnopqrstuv"]


@pytest.fixture
def local_backend(monkeypatch):
    yt_dlp = pytest.importorskip("yt_dlp", reason="real-backend checks require the download extra")
    from yt_dlp.extractor.common import InfoExtractor

    state = {"fetched": [], "fail": None, "title": "Original title"}

    class YoutubeIE(InfoExtractor):
        _VALID_URL = r"https://www\.youtube\.com/watch\?v=(?P<id>[A-Za-z0-9_-]{11})"

        def _real_extract(self, url):
            video_id = self._match_id(url)
            state["fetched"].append(video_id)
            return {
                "id": video_id,
                "title": state["title"],
                "formats": [{
                    "format_id": "720", "height": 720, "ext": "mp4",
                    "vcodec": "avc1", "acodec": "mp4a",
                    "url": f"https://example.invalid/{video_id}.mp4",
                }],
            }

    class YoutubeTabIE(InfoExtractor):
        _VALID_URL = r"https://www\.youtube\.com/playlist\?list=(?P<id>[A-Za-z0-9_-]+)"

        def _real_extract(self, url):
            return self.playlist_result([
                self.url_result(download.video_url(video_id), ie="Youtube", video_id=video_id,
                                video_title=f"Video {position}")
                for position, video_id in enumerate(VIDEO_IDS, 1)
            ], playlist_id=self._match_id(url), playlist_title="Offline playlist")

    original_init = yt_dlp.YoutubeDL.__init__

    def init_with_local_extractors(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self.add_info_extractor(YoutubeIE())
        self.add_info_extractor(YoutubeTabIE())

    def no_network(*args, **kwargs):
        raise AssertionError("Network access is forbidden in real-backend tests")

    def local_media(self, name, info, *args, **kwargs):
        if info["id"] == state["fail"]:
            raise yt_dlp.utils.DownloadError("Offline media failure")
        Path(name).write_bytes(b"offline-media-fixture")
        return True, True

    monkeypatch.setattr(yt_dlp.YoutubeDL, "__init__", init_with_local_extractors)
    monkeypatch.setattr(yt_dlp.YoutubeDL, "urlopen", no_network)
    monkeypatch.setattr(yt_dlp.YoutubeDL, "dl", local_media)
    return state


def test_real_backend_range_preview_and_ordered_downloads(tmp_path, local_backend):
    output = tmp_path / "media"
    plan = download.preview_playlist(PLAYLIST, output, start=2, end=3)

    assert [entry.position for entry in plan.entries] == [2, 3]
    assert [entry.video_id for entry in plan.entries] == VIDEO_IDS[1:]
    assert local_backend["fetched"] == []
    assert not output.exists()

    download.download_playlist(plan, quality=720)

    assert local_backend["fetched"] == VIDEO_IDS[1:]
    assert len(list(output.glob("00002 - *.mp4"))) == 1
    assert len(list(output.glob("00003 - *.mp4"))) == 1
    assert set(plan.archive.read_text(encoding="utf-8").splitlines()) == {
        f"youtube {video_id}" for video_id in VIDEO_IDS[1:]
    }


def test_real_backend_archive_survives_title_change_and_is_shared_with_single_video(tmp_path, local_backend):
    plan = download.preview_playlist(PLAYLIST, tmp_path / "media", start=1, end=1)
    download.download_playlist(plan)
    local_backend["title"] = "Changed title"
    local_backend["fetched"].clear()

    download.download_video(VIDEO_IDS[0], plan.output)
    second_plan = download.preview_playlist(PLAYLIST, plan.output, start=1, end=1)
    download.download_playlist(second_plan)

    assert second_plan.entries[0].skip_reason == "archived"
    assert local_backend["fetched"] == []
    assert len(list(plan.output.glob("*.mp4"))) == 1


def test_real_backend_failure_records_only_completed_downloads(tmp_path, local_backend):
    plan = download.preview_playlist(PLAYLIST, tmp_path / "media")
    local_backend["fail"] = VIDEO_IDS[1]

    with pytest.raises(download.DownloadError, match="Offline media failure"):
        download.download_playlist(plan)

    assert plan.archive.read_text(encoding="utf-8").splitlines() == [f"youtube {VIDEO_IDS[0]}"]
    local_backend["fail"] = None
    local_backend["fetched"].clear()
    # Reusing the old plan still rechecks the archive before starting.
    download.download_playlist(plan)
    assert local_backend["fetched"] == VIDEO_IDS[1:]


def test_real_backend_postprocessing_failure_does_not_record_completion(tmp_path, local_backend, monkeypatch):
    import yt_dlp

    def fail(*args, **kwargs):
        raise yt_dlp.utils.PostProcessingError("Offline postprocessing failure")

    monkeypatch.setattr(yt_dlp.YoutubeDL, "post_process", fail)
    with pytest.raises(download.DownloadError, match="Offline postprocessing failure"):
        download.download_video(VIDEO_IDS[0], tmp_path / "media")

    assert not (tmp_path / "media" / ".youtube3-download-archive.txt").exists()
