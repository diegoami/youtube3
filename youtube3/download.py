"""Optional public-video downloads, independent of the YouTube Data API."""

import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


class DownloadError(Exception):
    """A missing download dependency or a failed media download."""


@dataclass(frozen=True)
class TransferOptions:
    """Optional media transfer limits; None leaves each backend default intact."""

    limit_rate: int | None = None
    retries: int | None = None
    fragment_retries: int | None = None

    def __post_init__(self):
        if self.limit_rate is not None and (type(self.limit_rate) is not int or self.limit_rate <= 0):
            raise ValueError("Rate limit must be a positive integer number of bytes per second")
        for name in ("retries", "fragment_retries"):
            value = getattr(self, name)
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError(f"{name.replace('_', ' ').capitalize()} must be a nonnegative integer")

    def backend_options(self):
        return {key: value for key, value in (
            ("ratelimit", self.limit_rate), ("retries", self.retries),
            ("fragment_retries", self.fragment_retries),
        ) if value is not None}

    def description(self):
        parts = []
        if self.limit_rate is not None:
            parts.append(f"rate limit {self.limit_rate} bytes/s")
        if self.retries is not None:
            parts.append(f"HTTP retries {self.retries}")
        if self.fragment_retries is not None:
            parts.append(f"fragment retries {self.fragment_retries}")
        return "; ".join(parts) or "yt-dlp defaults"


@dataclass(frozen=True)
class MediaOptions:
    """Media selection and sidecar settings shared by video and playlist downloads."""

    audio_only: bool = False
    audio_format: str | None = None
    subtitles: tuple[str, ...] = ()
    auto_subtitles: bool = False
    write_metadata: bool = False
    write_thumbnail: bool = False
    format_id: str | None = None

    def __post_init__(self):
        if self.format_id is not None:
            if (not isinstance(self.format_id, str) or len(self.format_id) > 64
                    or not 1 <= len(self.format_id.split("+")) <= 2
                    or any(not re.fullmatch(r"[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*", part)
                           for part in self.format_id.split("+"))):
                raise ValueError("Format selection must be one exact ID or VIDEO_FORMAT_ID+AUDIO_FORMAT_ID "
                                 "(at most 64 characters)")
            if "+" in self.format_id and self.audio_only:
                raise ValueError("A video+audio format pair cannot be combined with --audio-only")
        if self.audio_format is not None:
            if not self.audio_only:
                raise ValueError("--audio-format requires --audio-only")
            if self.audio_format not in {"mp3", "m4a", "opus", "flac", "wav"}:
                raise ValueError("Audio format must be mp3, m4a, opus, flac or wav")
        if isinstance(self.subtitles, str) or any(
            not isinstance(language, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", language)
            for language in self.subtitles
        ):
            raise ValueError("Subtitle languages must be language codes such as en or de")
        object.__setattr__(self, "subtitles", tuple(self.subtitles))
        if self.auto_subtitles and not self.subtitles:
            raise ValueError("--auto-subtitles requires --subtitles with explicit languages")

    def description(self, quality=None):
        parts = [f"audio only ({self.audio_format or 'native'})" if self.audio_only else (
            f"video at most {quality}p" if quality else "best available video"
        )]
        if self.format_id is not None:
            parts[0] = f"exact format {self.format_id}" + (
                f"; audio only ({self.audio_format or 'native'})" if self.audio_only else ""
            )
        if self.subtitles:
            parts.append("subtitles=" + ",".join(self.subtitles) + (" (including automatic)" if self.auto_subtitles else ""))
        if self.write_metadata:
            parts.append("metadata JSON")
        if self.write_thumbnail:
            parts.append("thumbnail")
        return "; ".join(parts)


def video_url(value):
    """Accept a video ID, YouTube watch URL or youtu.be link, selecting one video."""
    video_id = value
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
        parsed = urlsplit(value)
        if parsed.scheme == "https" and parsed.netloc in {
            "youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be",
        }:
            if parsed.netloc == "youtu.be":
                video_id = parsed.path.removeprefix("/")
            elif parsed.path == "/watch":
                video_id = parse_qs(parsed.query).get("v", [""])[0]
        if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
            raise ValueError("Expected an 11-character video ID or an HTTPS YouTube watch/youtu.be URL")
    return f"https://www.youtube.com/watch?v={video_id}"


def _backend():
    try:
        import yt_dlp
    except ModuleNotFoundError as error:
        if error.name != "yt_dlp":
            raise
        raise DownloadError('Install download support with: pip install "youtube3[download]"') from None
    return yt_dlp


def _archive_path(output, archive, media):
    suffix = f"-audio-{media.audio_format or 'native'}" if media.audio_only else ""
    if media.format_id is not None:
        suffix += f"-format-{media.format_id}"
    return Path(archive).expanduser() if archive is not None else output / f".youtube3-download-archive{suffix}.txt"


def _archived_ids(archive):
    try:
        lines = archive.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return set()
    except (OSError, UnicodeError) as error:
        raise DownloadError(f"Cannot read download archive {archive}: {error}") from None
    return {line.split()[1] for line in lines if len(line.split()) == 2 and line.split()[0] == "youtube"}


def _options(output, quality, archive, media, transfer=None):
    if quality is not None and (type(quality) is not int or quality <= 0):
        raise ValueError("Quality must be a positive integer height in pixels")
    if media.audio_only and quality is not None:
        raise ValueError("--quality cannot be combined with --audio-only")
    if media.format_id is not None and quality is not None:
        raise ValueError("--quality cannot be combined with --format-id")
    height = f"[height<={quality}]" if quality else ""
    audio_marker = f" [audio-{media.audio_format or 'native'}]" if media.audio_only else ""
    format_marker = f" [format-{media.format_id}]" if media.format_id is not None else ""
    # Reserve the added marker's bytes within the existing filename size budget.
    title_bytes = 150 - len(audio_marker)
    options = {
        "format": f"bestvideo{height}+bestaudio/best{height}",
        "paths": {"home": str(output)},
        "outtmpl": f"%(title).{title_bytes}B [%(id)s]{audio_marker}{format_marker}.%(ext)s",
        "noplaylist": True,
        "overwrites": False,
        "continuedl": True,
        "cachedir": False,
        "download_archive": str(archive),
    }
    if media.audio_only:
        # Native audio deliberately has no combined video fallback.
        options["format"] = "bestaudio/best" if media.audio_format else "bestaudio"
    if media.format_id is not None:
        ids = media.format_id.split("+")
        # Filter by literal ID; a value such as 'best' never becomes a selector.
        # Quotes keep numeric IDs in string comparisons in yt-dlp's filter parser.
        if len(ids) == 2:
            options["format"] = f"bestvideo[format_id='{ids[0]}']+bestaudio[format_id='{ids[1]}']"
        else:
            selector = "bestaudio" if media.audio_only else "best*"
            options["format"] = f"{selector}[format_id='{ids[0]}']"
    if media.audio_format:
        options["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": media.audio_format}]
    if media.subtitles:
        options.update(writesubtitles=True, writeautomaticsub=media.auto_subtitles,
                       subtitleslangs=list(media.subtitles), subtitlesformat="vtt/best")
    if media.write_metadata:
        options.update(writeinfojson=True, clean_infojson=True)
    if media.write_thumbnail:
        options["writethumbnail"] = True
    options.update((transfer or TransferOptions()).backend_options())
    return options


def _require_audio_tools(media):
    if media.format_id is not None and "+" in media.format_id:
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            raise DownloadError("Merging explicit formats requires the FFmpeg and ffprobe executables on PATH")
    if media.audio_format and (not shutil.which("ffmpeg") or not shutil.which("ffprobe")):
        raise DownloadError("Audio conversion requires the FFmpeg and ffprobe executables on PATH")


def download_video(video, output, *, quality=None, dry_run=False, archive=None, media=None, transfer=None):
    """Download one public video; quality is an optional maximum height in pixels.

    A dry run only prints the local plan: no network, backend import or file writes.
    Existing files are preserved. yt-dlp handles partial-download resumption and
    records completed IDs in the archive, shared with playlist downloads.
    """
    url = video_url(video)
    media = media or MediaOptions()
    transfer = transfer or TransferOptions()
    destination = Path(output).expanduser()
    archive = _archive_path(destination, archive, media)
    options = _options(destination, quality, archive, media, transfer)
    if url.split("v=")[-1] in _archived_ids(archive):
        print(f"Skip {url}: archived in {archive}")
        return
    if dry_run:
        print(f"Dry run: download {url} to {destination} ({media.description(quality)}); "
              f"availability not checked; archive: {archive}; transfer: {transfer.description()}")
        return

    _require_audio_tools(media)
    yt_dlp = _backend()
    try:
        archive.parent.mkdir(parents=True, exist_ok=True)
        with yt_dlp.YoutubeDL(options) as downloader:
            result = downloader.download([url])
    except (yt_dlp.utils.DownloadError, OSError) as error:
        raise DownloadError(str(error)) from None
    if result:
        raise DownloadError("yt-dlp could not complete the download")


@dataclass(frozen=True)
class PlaylistEntry:
    position: int
    video_id: str | None
    title: str
    skip_reason: str | None = None


@dataclass(frozen=True)
class PlaylistPlan:
    url: str
    title: str
    output: Path
    archive: Path
    entries: tuple[PlaylistEntry, ...]
    media: MediaOptions = MediaOptions()
    transfer: TransferOptions = TransferOptions()


def playlist_url(value):
    """Accept a public playlist ID or HTTPS YouTube URL with an explicit list ID."""
    playlist_id = value
    if not re.fullmatch(r"[A-Za-z0-9_-]{10,}", playlist_id):
        parsed = urlsplit(value)
        if (parsed.scheme == "https"
                and parsed.netloc in {"youtube.com", "www.youtube.com", "m.youtube.com"}
                and parsed.path in {"/playlist", "/watch"}):
            playlist_id = parse_qs(parsed.query).get("list", [""])[0]
        if not re.fullmatch(r"[A-Za-z0-9_-]{10,}", playlist_id):
            raise ValueError("Expected a public playlist ID or an HTTPS YouTube URL with list=ID")
    return f"https://www.youtube.com/playlist?list={playlist_id}"


def preview_playlist(playlist, output, *, start=1, end=None, archive=None, media=None, transfer=None):
    """Read playlist metadata and return a fixed selection without writing files.

    Positions are 1-based, inclusive. Unlike a single-video dry run, enumerating
    a playlist requires read-only network access and the optional yt-dlp extra.
    """
    url = playlist_url(playlist)
    media = media or MediaOptions()
    if (type(start) is not int or start < 1
            or (end is not None and (type(end) is not int or end < start))):
        raise ValueError("Playlist range must use positive positions with end >= start")
    destination = Path(output).expanduser()
    archive = _archive_path(destination, archive, media)
    archived = _archived_ids(archive)
    yt_dlp = _backend()
    options = {
        "extract_flat": True,
        "skip_download": True,
        "playlist_items": f"{start}:{end if end is not None else ''}",
        "cachedir": False,
        "quiet": True,
    }
    try:
        with yt_dlp.YoutubeDL(options) as downloader:
            info = downloader.extract_info(url, download=False)
            if not info or info.get("_type") not in {"playlist", "multi_video"}:
                raise DownloadError("Could not read the playlist")
            selected = []
            seen = set()
            for offset, item in enumerate(info.get("entries") or []):
                item = item or {}
                video_id = item.get("id")
                reason = None
                if (not isinstance(video_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id)
                        or item.get("availability") in {"private", "needs_auth", "premium_only", "subscriber_only"}):
                    reason = "unavailable"
                elif video_id in archived:
                    reason = "archived"
                elif video_id in seen:
                    reason = "duplicate"
                if reason is None:
                    seen.add(video_id)
                selected.append(PlaylistEntry(
                    item.get("playlist_index") or start + offset,
                    video_id,
                    item.get("title") or "Unavailable video",
                    reason,
                ))
    except (yt_dlp.utils.DownloadError, OSError) as error:
        raise DownloadError(str(error)) from None
    return PlaylistPlan(url, info.get("title") or "Playlist", destination, archive, tuple(selected), media,
                        transfer or TransferOptions())


def download_playlist(plan, *, quality=None):
    """Download exactly the previewed IDs, preserving their playlist positions.

    yt-dlp records completed IDs after postprocessing succeeds. A failure stops
    this run; rerunning safely skips completed entries via the shared archive.
    """
    options = _options(plan.output, quality, plan.archive, plan.media, plan.transfer)
    options["outtmpl"] = "%(playlist_index)05d - " + options["outtmpl"]
    archived = _archived_ids(plan.archive)
    pending = [entry for entry in plan.entries if entry.skip_reason is None and entry.video_id not in archived]
    if not pending:
        return
    _require_audio_tools(plan.media)
    yt_dlp = _backend()
    try:
        plan.archive.parent.mkdir(parents=True, exist_ok=True)
        with yt_dlp.YoutubeDL(options) as downloader:
            for entry in pending:
                info = downloader.extract_info(
                    video_url(entry.video_id), download=True,
                    extra_info={
                        "playlist": plan.title,
                        "playlist_id": parse_qs(urlsplit(plan.url).query)["list"][0],
                        "playlist_index": entry.position,
                    },
                )
                if info is None and not downloader.in_download_archive({"id": entry.video_id, "ie_key": "Youtube"}):
                    raise DownloadError(f"Could not download video at playlist position {entry.position}")
    except (yt_dlp.utils.DownloadError, OSError) as error:
        raise DownloadError(str(error)) from None


def list_formats(video):
    """Read available formats without media/file writes, returning display fields only."""
    url = video_url(video)
    yt_dlp = _backend()
    options = {"skip_download": True, "noplaylist": True, "quiet": True,
               "cachedir": False, "ignore_no_formats_error": True}
    try:
        with yt_dlp.YoutubeDL(options) as downloader:
            info = downloader.extract_info(url, download=False)
            if not info:
                raise DownloadError("Could not read video formats")
            fields = ("format_id", "ext", "resolution", "width", "height", "vcodec", "acodec",
                      "filesize", "filesize_approx")
            return [{field: item.get(field) for field in fields} for item in info.get("formats") or []]
    except (yt_dlp.utils.DownloadError, OSError) as error:
        raise DownloadError(str(error)) from None
