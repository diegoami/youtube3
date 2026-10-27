"""Exercise real yt-dlp with local extractors and fake media transport only."""

import io
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from youtube3 import download
from youtube3 import download_batch as batch
from youtube3.cli import main


PLAYLIST = "PL0123456789abcdef"
VIDEO_IDS = ["BaW_jenozKc", "abcdefghijk", "lmnopqrstuv"]


@pytest.fixture
def local_backend(monkeypatch):
    yt_dlp = pytest.importorskip("yt_dlp", reason="real-backend checks require the download extra")
    from yt_dlp.extractor.common import InfoExtractor

    state = {"fetched": [], "fail": None, "title": "Original title", "media_formats": [],
             "asset_reads": [], "audio_bytes": None, "video_bytes": None,
             "extra_formats": [], "native_dl": yt_dlp.YoutubeDL.dl}

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
                }] + state["extra_formats"],
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
        content = state["audio_bytes"] if info.get("vcodec") == "none" else state["video_bytes"]
        Path(name).write_bytes(content or b"offline-media-fixture")
        return True, True

    monkeypatch.setattr(yt_dlp.YoutubeDL, "__init__", init_with_local_extractors)
    monkeypatch.setattr(yt_dlp.YoutubeDL, "urlopen", no_network)
    monkeypatch.setattr(yt_dlp.YoutubeDL, "dl", local_media)
    return state


@pytest.mark.parametrize("source_kind", ["file", "browser"])
def test_real_download_uses_synthetic_cookies_without_rewriting_source(tmp_path, local_backend, monkeypatch, source_kind):
    import yt_dlp
    import yt_dlp.cookies

    source = tmp_path / "synthetic-session.txt"
    content = "# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t0\tsynthetic\tfixture-value\n"
    source.write_text(content)
    browsers = []

    def synthetic_browser(browser, profile, logger, **kwargs):
        browsers.append((browser, profile))
        jar = yt_dlp.cookies.YoutubeDLCookieJar(io.StringIO(content))
        jar.load()
        return jar

    monkeypatch.setattr(yt_dlp.cookies, "extract_cookies_from_browser", synthetic_browser)
    original = yt_dlp.YoutubeDL.extract_info
    loaded = []

    def extract(self, *args, **kwargs):
        loaded.append(len(list(self.cookiejar)))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(yt_dlp.YoutubeDL, "extract_info", extract)
    access = (download.AccessOptions(cookies=source) if source_kind == "file" else
              download.AccessOptions(browser="firefox", browser_profile="synthetic-profile"))
    download.download_video(VIDEO_IDS[0], tmp_path / "media", access=access)
    assert loaded and all(count == 1 for count in loaded)
    assert list((tmp_path / "media").glob("*.mp4"))
    assert source.read_text() == content
    assert browsers == ([] if source_kind == "file" else [("firefox", "synthetic-profile")])


@pytest.mark.parametrize("message", ["HTTP Error 429: Too Many Requests", "Sign in to confirm you're not a bot"])
def test_real_backend_blocks_stop_batch_despite_continuation(tmp_path, local_backend, monkeypatch, message):
    import yt_dlp

    attempts = []

    def blocked(self, *args, **kwargs):
        attempts.append(1)
        raise yt_dlp.utils.DownloadError(message)

    plan = download.preview_playlist(PLAYLIST, tmp_path / "media")
    monkeypatch.setattr(yt_dlp.YoutubeDL, "dl", blocked)
    result = batch.download_batch(plan, continue_on_error=True, report=tmp_path / "result.json")
    assert len(attempts) == 1
    assert [entry.status for entry in result.entries] == ["failed", "not_attempted", "not_attempted"]
    assert result.entries[0].reason == "blocked"


def test_real_playlist_paces_extractions_and_keeps_order(tmp_path, local_backend, monkeypatch):
    sleeps = []
    monkeypatch.setattr(download.time, "sleep", lambda seconds: sleeps.append((seconds, len(local_backend["fetched"]))))
    plan = download.preview_playlist(PLAYLIST, tmp_path / "media", transfer=download.TransferOptions(sleep_interval=7))
    download.download_playlist(plan)
    assert sleeps == [(7, 1), (7, 2)]
    assert local_backend["fetched"] == VIDEO_IDS


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


@pytest.mark.parametrize("format_id", [None, "audio"])
def test_real_ffmpeg_converts_generated_audio_and_records_completion(tmp_path, local_backend, format_id):
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip("Actual conversion check requires FFmpeg and ffprobe")
    sample = tmp_path / "sample.m4a"
    subprocess.run([ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                    "sine=frequency=440:duration=0.1", "-c:a", "aac", str(sample)], check=True, capture_output=True)
    local_backend["audio_bytes"] = sample.read_bytes()
    output = tmp_path / "converted"

    download.download_video(VIDEO_IDS[0], output, media=download.MediaOptions(
        audio_only=True, audio_format="mp3", format_id=format_id))

    converted = next(output.glob("*.mp3"))
    probe = subprocess.run([ffprobe, "-v", "error", "-show_streams", "-of", "json", str(converted)],
                           check=True, capture_output=True, text=True)
    streams = json.loads(probe.stdout)["streams"]
    assert [(stream["codec_type"], stream["codec_name"]) for stream in streams] == [("audio", "mp3")]
    suffix = "-format-audio" if format_id else ""
    assert (output / f".youtube3-download-archive-audio-mp3{suffix}.txt").read_text().strip() == f"youtube {VIDEO_IDS[0]}"


def test_batch_continues_then_retries_only_failure_with_saved_settings(tmp_path, local_backend, monkeypatch):
    media = download.MediaOptions(audio_only=True, subtitles=("en",), write_metadata=True)
    plan = download.preview_playlist(PLAYLIST, tmp_path / "media", media=media)
    report = tmp_path / "reports" / "first.json"
    local_backend["fail"] = VIDEO_IDS[1]

    result = batch.download_batch(plan, continue_on_error=True, report=report)

    assert [entry.status for entry in result.entries] == ["downloaded", "failed", "downloaded"]
    assert result.failed == 1
    assert local_backend["fetched"] == VIDEO_IDS
    assert plan.archive.read_text().splitlines() == [f"youtube {VIDEO_IDS[0]}", f"youtube {VIDEO_IDS[2]}"]
    payload = json.loads(report.read_text())
    assert payload["entries"][1]["reason"] == "download_failed"
    assert "example.invalid" not in report.read_text()
    assert "Offline media failure" not in report.read_text()
    local_backend["fail"] = None
    local_backend["fetched"].clear()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    retry, quality = batch.retry_plan(report)

    assert retry.media == media
    assert quality is None
    assert [(entry.position, entry.video_id) for entry in retry.entries] == [(2, VIDEO_IDS[1])]
    second = batch.download_batch(retry, report=tmp_path / "retry.json")

    assert not second.failed
    assert local_backend["fetched"] == [VIDEO_IDS[1]]
    assert len(list(plan.output.glob("00002 - *.m4a"))) == 1
    assert len(list(plan.output.glob("00002 - *.en.vtt"))) == 1
    assert len(list(plan.output.glob("00002 - *.info.json"))) == 1
    # An older failed report must not redownload an ID completed since then.
    local_backend["fetched"].clear()
    assert batch.download_batch(retry).entries[0].status == "skipped"
    assert local_backend["fetched"] == []


def test_batch_default_stops_and_report_excludes_unattempted_from_retry(tmp_path, local_backend):
    plan = download.preview_playlist(PLAYLIST, tmp_path / "media")
    local_backend["fail"] = VIDEO_IDS[0]
    report = tmp_path / "first.json"

    result = batch.download_batch(plan, quality=720, report=report)

    assert [entry.status for entry in result.entries] == ["failed", "not_attempted", "not_attempted"]
    assert local_backend["fetched"] == VIDEO_IDS[:1]
    retry, quality = batch.retry_plan(report)
    assert quality == 720
    assert [entry.video_id for entry in retry.entries] == VIDEO_IDS[:1]


def test_report_never_overwrites_existing_file_or_downloads_first(tmp_path, local_backend):
    plan = download.preview_playlist(PLAYLIST, tmp_path / "media")
    report = tmp_path / "results.json"
    report.write_text("keep me")

    with pytest.raises(download.DownloadError, match="Cannot write download report"):
        batch.download_batch(plan, report=report)

    assert report.read_text() == "keep me"
    assert local_backend["fetched"] == []
    assert not plan.output.exists()


def test_interrupted_batch_keeps_last_checkpoint_and_pending_entries(tmp_path, local_backend, monkeypatch):
    plan = download.preview_playlist(PLAYLIST, tmp_path / "media")
    original = download.download_playlist
    report = tmp_path / "results.json"

    def interrupt(selection, **kwargs):
        payload = json.loads(report.read_text())
        if selection.entries[0].position == 2:
            assert [entry["status"] for entry in payload["entries"]] == [
                "downloaded", "not_attempted", "not_attempted"]
            raise KeyboardInterrupt
        assert all(entry["status"] == "not_attempted" for entry in payload["entries"])
        return original(selection, **kwargs)

    monkeypatch.setattr(download, "download_playlist", interrupt)
    with pytest.raises(KeyboardInterrupt):
        batch.download_batch(plan, report=report)

    assert [entry["status"] for entry in json.loads(report.read_text())["entries"]] == [
        "downloaded", "not_attempted", "not_attempted"]
    assert not list(tmp_path.glob(".youtube3-report-*"))


def test_playlist_batch_cli_exits_nonzero_after_continuing(tmp_path, local_backend, monkeypatch, capsys):
    report = tmp_path / "results.json"
    local_backend["fail"] = VIDEO_IDS[1]
    monkeypatch.setattr("sys.argv", ["youtube3", "download", "playlist", PLAYLIST, "--apply",
                                     "--output", str(tmp_path / "media"), "--continue-on-error",
                                     "--report", str(report)])
    with pytest.raises(SystemExit) as error:
        main.main()

    assert error.value.code == 1
    assert local_backend["fetched"] == VIDEO_IDS
    assert "2 downloaded; 1 failed" in capsys.readouterr().out
    assert json.loads(report.read_text())["entries"][1]["status"] == "failed"


def test_retry_cli_offline_preview(tmp_path, local_backend, monkeypatch, capsys):
    plan = download.preview_playlist(PLAYLIST, tmp_path / "media")
    report = tmp_path / "results.json"
    local_backend["fail"] = VIDEO_IDS[1]
    batch.download_batch(plan, continue_on_error=True, report=report)
    before = report.read_bytes()
    local_backend["fetched"].clear()
    monkeypatch.setitem(sys.modules, "yt_dlp", None)
    monkeypatch.setattr("sys.argv", ["youtube3", "download", "retry", str(report)])

    main.main()

    assert "00002 [retry]" in capsys.readouterr().out
    assert report.read_bytes() == before
    assert local_backend["fetched"] == []
    assert not list(tmp_path.glob("retry.json"))


@pytest.mark.parametrize("still_fails", [False, True])
def test_retry_cli_apply_downloads_failed_selection_and_reports_exit(tmp_path, local_backend, monkeypatch, still_fails):
    plan = download.preview_playlist(PLAYLIST, tmp_path / "media")
    report = tmp_path / "results.json"
    local_backend["fail"] = VIDEO_IDS[1]
    batch.download_batch(plan, continue_on_error=True, report=report)
    local_backend["fetched"].clear()
    if not still_fails:
        local_backend["fail"] = None
    retry_report = tmp_path / "retry.json"
    monkeypatch.setattr("sys.argv", ["youtube3", "download", "retry", str(report), "--apply",
                                     "--report", str(retry_report)])
    if still_fails:
        with pytest.raises(SystemExit) as error:
            main.main()
        assert error.value.code == 1
    else:
        main.main()
    assert local_backend["fetched"] == [VIDEO_IDS[1]]
    entry = json.loads(retry_report.read_text())["entries"][0]
    assert entry["position"] == 2
    assert entry["status"] == ("failed" if still_fails else "downloaded")


def test_report_checkpoint_failure_stops_before_next_download(tmp_path, local_backend, monkeypatch):
    plan = download.preview_playlist(PLAYLIST, tmp_path / "media")
    report = tmp_path / "results.json"

    def fail(*args):
        raise OSError("Offline write failure")

    monkeypatch.setattr(batch.os, "replace", fail)
    with pytest.raises(download.DownloadError, match="Offline write failure"):
        batch.download_batch(plan, continue_on_error=True, report=report)

    assert local_backend["fetched"] == VIDEO_IDS[:1]
    assert not list(tmp_path.glob(".youtube3-report-*"))
    assert json.loads(report.read_text())["entries"][0]["status"] == "not_attempted"
    # The archive remains authoritative if the checkpoint could not advance.
    assert plan.archive.read_text().strip() == f"youtube {VIDEO_IDS[0]}"


@pytest.mark.parametrize("target", ["output", "archive"])
def test_report_cannot_collide_with_archive_or_output(tmp_path, local_backend, target):
    plan = download.preview_playlist(PLAYLIST, tmp_path / "media")
    with pytest.raises(download.DownloadError, match="Report must differ"):
        batch.download_batch(plan, report=getattr(plan, target))
    assert local_backend["fetched"] == []
    assert not plan.output.exists()


@pytest.mark.parametrize("retries", [0, 1])
def test_real_http_downloader_obeys_retry_count_and_rate_options(tmp_path, local_backend, monkeypatch, retries):
    import yt_dlp
    from yt_dlp.downloader.common import FileDownloader
    from yt_dlp.networking import Response
    from yt_dlp.networking.exceptions import HTTPError

    attempts = []
    limits = []
    content = b"synthetic media bytes"
    original_slow_down = FileDownloader.slow_down

    def transport(self, request):
        assert request.url.startswith("https://example.invalid/")
        attempts.append(request.url)
        if len(attempts) == 1:
            raise HTTPError(Response(io.BytesIO(), request.url, {}, status=503))
        return Response(io.BytesIO(content), request.url, {"Content-Length": str(len(content))})

    def slow_down(self, *args):
        limits.append(tuple(self.params.get(key) for key in ("ratelimit", "retries", "fragment_retries")))
        return original_slow_down(self, *args)

    monkeypatch.setattr(yt_dlp.YoutubeDL, "dl", local_backend["native_dl"])
    monkeypatch.setattr(yt_dlp.YoutubeDL, "urlopen", transport)
    monkeypatch.setattr(FileDownloader, "slow_down", slow_down)
    transfer = download.TransferOptions(limit_rate=1048576, retries=retries, fragment_retries=2)
    if retries == 0:
        with pytest.raises(download.DownloadError, match="503"):
            download.download_video(VIDEO_IDS[0], tmp_path, transfer=transfer)
        assert len(attempts) == 1
        assert not (tmp_path / ".youtube3-download-archive.txt").exists()
    else:
        download.download_video(VIDEO_IDS[0], tmp_path, transfer=transfer)
        assert len(attempts) == 2
        assert next(tmp_path.glob("*.mp4")).read_bytes() == content
        assert limits and all(values == (1048576, 1, 2) for values in limits)
        assert (tmp_path / ".youtube3-download-archive.txt").read_text().strip() == f"youtube {VIDEO_IDS[0]}"


def test_playlist_limits_are_saved_and_reused_by_retry(tmp_path, local_backend, monkeypatch, capsys):
    import yt_dlp

    report = tmp_path / "first.json"
    monkeypatch.setattr(sys, "argv", ["youtube3", "download", "playlist", PLAYLIST, "--apply",
                                     "--output", str(tmp_path / "media"), "--continue-on-error",
                                     "--report", str(report), "--limit-rate", "500K",
                                     "--retries", "0", "--fragment-retries", "3"])
    local_backend["fail"] = VIDEO_IDS[1]
    with pytest.raises(SystemExit) as error:
        main.main()
    assert error.value.code == 1
    assert "rate limit 512000 bytes/s" in capsys.readouterr().out
    payload = json.loads(report.read_text())
    assert payload["schema_version"] == 4
    assert payload["requires_cookies"] is False
    assert payload["transfer"] == {"limit_rate": 512000, "retries": 0, "fragment_retries": 3, "sleep_interval": 5}
    plan, quality = batch.retry_plan(report)
    local_backend["fail"] = None
    local_backend["fetched"].clear()
    options = []
    original = yt_dlp.YoutubeDL.dl

    def local_media(self, *args, **kwargs):
        options.append(tuple(self.params.get(key) for key in ("ratelimit", "retries", "fragment_retries")))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(yt_dlp.YoutubeDL, "dl", local_media)
    result = batch.download_batch(plan, quality=quality)
    assert not result.failed
    assert local_backend["fetched"] == [VIDEO_IDS[1]]
    assert options == [(512000, 0, 3)]


def test_exact_choices_use_separate_files_and_archives_from_previous_downloads(tmp_path, local_backend):
    local_backend["extra_formats"] = [{
        "format_id": "360", "height": 360, "ext": "mp4", "vcodec": "avc1", "acodec": "mp4a",
        "url": "https://example.invalid/lower.mp4",
    }]
    download.download_video(VIDEO_IDS[0], tmp_path)
    for format_id in ("720", "360"):
        download.download_video(VIDEO_IDS[0], tmp_path, media=download.MediaOptions(format_id=format_id))
    assert local_backend["media_formats"] == ["720", "720", "360"]
    assert len(list(tmp_path.glob("*.mp4"))) == 3
    assert len(list(tmp_path.glob("*format-360*.mp4"))) == 1
    assert len(list(tmp_path.glob("*format-720*.mp4"))) == 1
    assert (tmp_path / ".youtube3-download-archive-format-360.txt").read_text().strip() == f"youtube {VIDEO_IDS[0]}"
    local_backend["fetched"].clear()
    download.download_video(VIDEO_IDS[0], tmp_path, media=download.MediaOptions(format_id="360"))
    assert local_backend["fetched"] == []


@pytest.mark.parametrize("format_id", ["missing", "best"])
def test_exact_id_is_literal_and_has_no_fallback(tmp_path, local_backend, format_id):
    with pytest.raises(download.DownloadError, match="format"):
        download.download_video(VIDEO_IDS[0], tmp_path, media=download.MediaOptions(format_id=format_id))
    assert not local_backend["media_formats"]
    assert not list(tmp_path.iterdir())


def test_audio_only_exact_selection_rejects_a_combined_stream(tmp_path, local_backend):
    download.download_video(VIDEO_IDS[0], tmp_path, media=download.MediaOptions(audio_only=True, format_id="audio"))
    assert local_backend["media_formats"] == ["audio"]
    with pytest.raises(download.DownloadError, match="format"):
        download.download_video(VIDEO_IDS[0], tmp_path, media=download.MediaOptions(audio_only=True, format_id="720"))
    assert local_backend["media_formats"] == ["audio"]


@pytest.mark.parametrize("format_id", ["audio+720", "720+audio"])
def test_exact_pair_requires_video_only_then_audio_only(tmp_path, local_backend, monkeypatch, format_id):
    monkeypatch.setattr(download.shutil, "which", lambda name: "/synthetic/" + name)
    with pytest.raises(download.DownloadError, match="format"):
        download.download_video(VIDEO_IDS[0], tmp_path, media=download.MediaOptions(format_id=format_id))
    assert not local_backend["media_formats"]
    assert not list(tmp_path.iterdir())


def test_exact_playlist_choice_survives_failed_report_and_retry(tmp_path, local_backend, monkeypatch, capsys):
    report = tmp_path / "first.json"
    local_backend["fail"] = VIDEO_IDS[1]
    monkeypatch.setattr(sys, "argv", ["youtube3", "download", "playlist", PLAYLIST, "--apply",
                                     "--output", str(tmp_path / "media"), "--format-id", "720",
                                     "--continue-on-error", "--report", str(report)])
    with pytest.raises(SystemExit) as error:
        main.main()
    assert error.value.code == 1
    assert "exact format 720" in capsys.readouterr().out
    payload = json.loads(report.read_text())
    assert payload["schema_version"] == 4
    assert payload["media"]["format_id"] == "720"
    plan, quality = batch.retry_plan(report)
    local_backend["fail"] = None
    local_backend["media_formats"].clear()
    result = batch.download_batch(plan, quality=quality)
    assert not result.failed
    assert local_backend["media_formats"] == ["720"]
    assert len(list(plan.output.glob("00002 - *format-720*.mp4"))) == 1


def test_real_ffmpeg_merges_exact_generated_video_and_audio(tmp_path, local_backend):
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip("Actual merge check requires FFmpeg and ffprobe")
    video, audio = tmp_path / "sample.mp4", tmp_path / "sample.m4a"
    subprocess.run([ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                    "color=c=black:s=16x16:r=10:d=0.2", "-an", "-c:v", "mpeg4", str(video)],
                   check=True, capture_output=True)
    subprocess.run([ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                    "sine=frequency=440:duration=0.2", "-c:a", "aac", str(audio)], check=True, capture_output=True)
    local_backend["video_bytes"] = video.read_bytes()
    local_backend["audio_bytes"] = audio.read_bytes()
    local_backend["extra_formats"] = [{
        "format_id": "silent", "height": 16, "width": 16, "ext": "mp4", "vcodec": "mpeg4", "acodec": "none",
        "url": "https://example.invalid/silent.mp4",
    }]
    output = tmp_path / "merged"
    download.download_video(VIDEO_IDS[0], output, media=download.MediaOptions(format_id="silent+audio"))
    assert local_backend["media_formats"] == ["silent", "audio"]
    merged = next(output.glob("*format-silent+audio*.mp4"))
    probe = subprocess.run([ffprobe, "-v", "error", "-show_streams", "-of", "json", str(merged)],
                           check=True, capture_output=True, text=True)
    streams = json.loads(probe.stdout)["streams"]
    assert {(stream["codec_type"], stream["codec_name"]) for stream in streams} == {
        ("video", "mpeg4"), ("audio", "aac")}
    assert (output / ".youtube3-download-archive-format-silent+audio.txt").read_text().strip() == f"youtube {VIDEO_IDS[0]}"
