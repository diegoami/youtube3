"""Optional public-video downloads, independent of the YouTube Data API."""

import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


class DownloadError(Exception):
    """A missing download dependency or a failed media download."""


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


def download_video(video, output, *, quality=None, dry_run=False):
    """Download one public video; quality is an optional maximum height in pixels.

    A dry run only prints the local plan: no network, backend import or file writes.
    Existing files are preserved. yt-dlp handles partial-download resumption.
    """
    url = video_url(video)
    if quality is not None and (not isinstance(quality, int) or quality <= 0):
        raise ValueError("Quality must be a positive integer height in pixels")
    destination = Path(output).expanduser()
    if dry_run:
        limit = f"at most {quality}p" if quality else "best available quality"
        print(f"Dry run: download {url} to {destination} ({limit}); availability not checked")
        return

    try:
        import yt_dlp
    except ModuleNotFoundError as error:
        if error.name != "yt_dlp":
            raise
        raise DownloadError('Install download support with: pip install "youtube3[download]"') from None

    height = f"[height<={quality}]" if quality else ""
    options = {
        "format": f"bestvideo{height}+bestaudio/best{height}",
        "paths": {"home": str(destination)},
        "outtmpl": "%(title).150B [%(id)s].%(ext)s",
        "noplaylist": True,
        "overwrites": False,
        "continuedl": True,
        # Do not use the owner's shared yt-dlp cache for this isolated POC.
        "cachedir": False,
    }
    try:
        with yt_dlp.YoutubeDL(options) as downloader:
            result = downloader.download([url])
    except (yt_dlp.utils.DownloadError, OSError) as error:
        raise DownloadError(str(error)) from None
    if result:
        raise DownloadError("yt-dlp could not complete the download")
