"""Download one public video with the optional yt-dlp extra."""

import argparse
from pathlib import Path

from youtube3.download import DownloadError, download_video
from youtube3.cli.download_options import add_media_arguments, media_options, positive_height


def main():
    parser = argparse.ArgumentParser(
        prog="youtube3 download video",
        description="Download one public YouTube video (optional download extra; no Google login).",
    )
    parser.add_argument("video", help="video ID, HTTPS YouTube watch URL or youtu.be link")
    parser.add_argument("--output", type=Path, default=Path("downloads"), help="output folder (default: downloads)")
    parser.add_argument("--quality", type=positive_height, help="maximum video height in pixels, e.g. 720 or 1080")
    parser.add_argument("--archive", type=Path, help="completed-ID archive (default: in the output folder)")
    parser.add_argument("--dry-run", action="store_true", help="print the plan without network access or file writes")
    add_media_arguments(parser)
    args = parser.parse_args()
    media = media_options(args, parser)
    try:
        download_video(args.video, args.output, quality=args.quality, dry_run=args.dry_run,
                       archive=args.archive, media=media)
    except (ValueError, DownloadError) as error:
        parser.exit(1, f"Error: {error}\n")


if __name__ == "__main__":
    main()
