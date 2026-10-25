"""Exercise real yt-dlp with local extractors and fake media transport only."""

import io
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from youtube3 import download


PLAYLIST = "PL0123456789abcdef"
VIDEO_IDS = ["BaW_jenozKc", "abcdefghijk", "lmnopqrstuv"]


@pytest.fixture
def local_backend(monkeypatch):
    yt_dlp = pytest.importorskip("yt_dlp", reason="real-backend checks require the download extra")
    from yt_dlp.extractor.common import InfoExtractor

    state = {"fetched": [], "fail": None, "title": "Original title", "media_formats": [],
             "asset_reads": [], "audio_bytes": None}

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
                }, {
                    "format_id": "audio", "ext": "m4a", "vcodec": "none", "acodec": "mp4a.40.2",
                    "url": f"https://example.invalid/{video_id}.m4a",
                }],
                "subtitles": {"en": [{"ext": "vtt", "data": "WEBVTT\n\n00:00.000 --> 00:01.000\nCaption\n"}]},
                "automatic_captions": {"de": [{"ext": "vtt", "data": "WEBVTT\n\n00:00.000 --> 00:01.000\nAuto caption\n"}]},
                "thumbnail": "https://example.invalid/thumbnail.jpg",
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
        request = args[-1]
        if getattr(request, "url", None) == "https://example.invalid/thumbnail.jpg":
            state["asset_reads"].append("thumbnail")
            return io.BytesIO(b"offline-thumbnail-fixture")
        raise AssertionError("Network access is forbidden in real-backend tests")

    def local_media(self, name, info, *args, **kwargs):
        if info["id"] == state["fail"]:
            raise yt_dlp.utils.DownloadError("Offline media failure")
        state["media_formats"].append(info["format_id"])
        content = state["audio_bytes"] if info.get("vcodec") == "none" else None
        Path(name).write_bytes(content or b"offline-media-fixture")
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


def test_real_backend_format_preview_never_fetches_media_or_assets(tmp_path, local_backend, monkeypatch):
    monkeypatch.chdir(tmp_path)

    formats = download.list_formats(VIDEO_IDS[0])

    assert {item["format_id"] for item in formats} == {"720", "audio"}
    assert local_backend["media_formats"] == []
    assert local_backend["asset_reads"] == []
    assert list(tmp_path.iterdir()) == []
    assert all("url" not in item for item in formats)


def test_real_backend_native_audio_and_video_use_separate_archives(tmp_path, local_backend):
    download.download_video(VIDEO_IDS[0], tmp_path)
    download.download_video(VIDEO_IDS[0], tmp_path, media=download.MediaOptions(audio_only=True))

    assert local_backend["media_formats"] == ["720", "audio"]
    assert len(list(tmp_path.glob("*.mp4"))) == 1
    assert len(list(tmp_path.glob("*.m4a"))) == 1
    assert (tmp_path / ".youtube3-download-archive-audio-native.txt").read_text().strip() == f"youtube {VIDEO_IDS[0]}"


def test_real_backend_writes_selected_sidecars(tmp_path, local_backend):
    media = download.MediaOptions(subtitles=("en", "de"), auto_subtitles=True,
                                  write_metadata=True, write_thumbnail=True)
    download.download_video(VIDEO_IDS[0], tmp_path, media=media)

    metadata = json.loads(next(tmp_path.glob("*.info.json")).read_text(encoding="utf-8"))
    assert metadata["id"] == VIDEO_IDS[0]
    assert "Caption" in next(tmp_path.glob("*.en.vtt")).read_text(encoding="utf-8")
    assert "Auto caption" in next(tmp_path.glob("*.de.vtt")).read_text(encoding="utf-8")
    assert next(tmp_path.glob("*.jpg")).read_bytes() == b"offline-thumbnail-fixture"
    assert local_backend["asset_reads"] == ["thumbnail"]


def test_real_backend_sidecars_are_disabled_by_default(tmp_path, local_backend):
    download.download_video(VIDEO_IDS[0], tmp_path)
    assert not list(tmp_path.glob("*.info.json"))
    assert not list(tmp_path.glob("*.vtt"))
    assert not list(tmp_path.glob("*.jpg"))
    assert local_backend["asset_reads"] == []


def test_real_ffmpeg_converts_generated_audio_and_records_completion(tmp_path, local_backend):
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip("Actual conversion check requires FFmpeg and ffprobe")
    sample = tmp_path / "sample.m4a"
    subprocess.run([ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                    "sine=frequency=440:duration=0.1", "-c:a", "aac", str(sample)], check=True, capture_output=True)
    local_backend["audio_bytes"] = sample.read_bytes()
    output = tmp_path / "converted"

    download.download_video(VIDEO_IDS[0], output, media=download.MediaOptions(audio_only=True, audio_format="mp3"))

    converted = next(output.glob("*.mp3"))
    probe = subprocess.run([ffprobe, "-v", "error", "-show_streams", "-of", "json", str(converted)],
                           check=True, capture_output=True, text=True)
    streams = json.loads(probe.stdout)["streams"]
    assert [(stream["codec_type"], stream["codec_name"]) for stream in streams] == [("audio", "mp3")]
    assert (output / ".youtube3-download-archive-audio-mp3.txt").read_text().strip() == f"youtube {VIDEO_IDS[0]}"
