"""Real downloaders/postprocessors must preserve other media modes in one folder."""

import io
import json
import shutil
import subprocess

import pytest

from youtube3 import download


VIDEO = "BaW_jenozKc"
PLAYLIST = "PL0123456789abcdef"


@pytest.fixture(scope="module")
def webm_samples(tmp_path_factory):
    pytest.importorskip("yt_dlp", reason="mode collision checks require the download extra")
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip("Mode preservation checks require FFmpeg and ffprobe")
    root = tmp_path_factory.mktemp("mode-samples")
    video, audio = root / "video.webm", root / "audio.webm"
    subprocess.run([ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                    "color=c=black:s=16x16:r=10:d=0.2", "-f", "lavfi", "-i", "sine=duration=0.2",
                    "-shortest", "-c:v", "libvpx-vp9", "-c:a", "libopus", str(video)],
                   check=True, capture_output=True)
    subprocess.run([ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-i", str(video),
                    "-vn", "-c:a", "copy", str(audio)], check=True, capture_output=True)
    return {"video": video.read_bytes(), "audio": audio.read_bytes(), "ffprobe": ffprobe}


@pytest.fixture
def webm_backend(monkeypatch, webm_samples):
    import yt_dlp
    from yt_dlp.extractor.common import InfoExtractor
    from yt_dlp.networking import Response

    requests = []

    class YoutubeIE(InfoExtractor):
        _VALID_URL = r"https://www\.youtube\.com/watch\?v=(?P<id>[A-Za-z0-9_-]{11})"

        def _real_extract(self, url):
            return {"id": self._match_id(url), "title": "T", "formats": [
                {"format_id": "18", "ext": "webm", "vcodec": "vp9", "acodec": "opus", "height": 16,
                 "url": "https://example.invalid/video"},
                {"format_id": "251", "ext": "webm", "vcodec": "none", "acodec": "opus", "abr": 160,
                 "url": "https://example.invalid/audio"},
            ]}

    class YoutubeTabIE(InfoExtractor):
        _VALID_URL = r"https://www\.youtube\.com/playlist\?list=(?P<id>[A-Za-z0-9_-]+)"

        def _real_extract(self, url):
            return self.playlist_result([self.url_result(download.video_url(VIDEO), ie="Youtube", video_id=VIDEO)],
                                        playlist_id=self._match_id(url), playlist_title="Synthetic playlist")

    original_init = yt_dlp.YoutubeDL.__init__

    def init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self.add_info_extractor(YoutubeIE())
        self.add_info_extractor(YoutubeTabIE())

    def transport(self, request):
        assert request.url in {"https://example.invalid/video", "https://example.invalid/audio"}
        mode = request.url.rsplit("/", 1)[-1]
        requests.append(mode)
        content = webm_samples[mode]
        return Response(io.BytesIO(content), request.url, {"Content-Length": str(len(content))})

    monkeypatch.setattr(yt_dlp.YoutubeDL, "__init__", init)
    monkeypatch.setattr(yt_dlp.YoutubeDL, "urlopen", transport)
    return requests


def codecs(path, ffprobe):
    result = subprocess.run([ffprobe, "-v", "error", "-show_streams", "-of", "json", str(path)],
                            check=True, capture_output=True, text=True)
    return {(stream["codec_type"], stream["codec_name"]) for stream in json.loads(result.stdout)["streams"]}


@pytest.mark.parametrize("playlist", [False, True])
@pytest.mark.parametrize(("first", "second"), [
    (download.MediaOptions(), download.MediaOptions(audio_only=True)),
    (download.MediaOptions(), download.MediaOptions(audio_only=True, audio_format="mp3")),
    (download.MediaOptions(audio_only=True), download.MediaOptions()),
    (download.MediaOptions(audio_only=True), download.MediaOptions(audio_only=True, audio_format="m4a")),
    (download.MediaOptions(audio_only=True, format_id="251"),
     download.MediaOptions(audio_only=True, audio_format="mp3", format_id="251")),
])
def test_other_media_mode_survives_download_and_conversion(tmp_path, webm_backend, webm_samples,
                                                         playlist, first, second):
    def run(media):
        if playlist:
            plan = download.preview_playlist(PLAYLIST, tmp_path, media=media)
            download.download_playlist(plan)
        else:
            download.download_video(VIDEO, tmp_path, media=media)

    run(first)
    original = next(tmp_path.glob("*.webm"))
    before = original.read_bytes()
    expected_first = {("audio", "opus")} if first.audio_only else {("video", "vp9"), ("audio", "opus")}
    assert codecs(original, webm_samples["ffprobe"]) == expected_first
    webm_backend.clear()

    run(second)

    assert original.exists(), "A different mode must not delete the original media"
    assert original.read_bytes() == before
    outputs = [path for path in tmp_path.iterdir() if path != original and not path.name.startswith(".")]
    assert len(outputs) == 1, "The second mode must produce a separate media file"
    expected_second = ({("audio", {"mp3": "mp3", "m4a": "aac"}.get(second.audio_format, "opus"))}
                       if second.audio_only else {("video", "vp9"), ("audio", "opus")})
    assert codecs(outputs[0], webm_samples["ffprobe"]) == expected_second
    assert webm_backend == ["audio" if second.audio_only else "video"]
    options_archive = download._archive_path(tmp_path, None, second)
    assert options_archive.read_text().strip() == f"youtube {VIDEO}"
    webm_backend.clear()
    run(first)
    run(second)
    assert not webm_backend
