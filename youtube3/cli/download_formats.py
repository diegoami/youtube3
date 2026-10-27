"""Inspect public-video formats without downloading media or writing files."""

import argparse

from youtube3.download import DownloadError, list_formats
from youtube3.cli.download_options import add_access_arguments, access_options


def main():
    parser = argparse.ArgumentParser(
        prog="youtube3 download formats",
        description="List public-video formats (reads metadata online; no media downloads or file writes).",
    )
    parser.add_argument("video", help="video ID, HTTPS YouTube watch URL or youtu.be link")
    add_access_arguments(parser)
    args = parser.parse_args()
    try:
        formats = list_formats(args.video, access=access_options(args, parser))
    except (ValueError, DownloadError) as error:
        parser.exit(1, f"Error: {error}\n")
    print(f"{'ID':<12} {'EXT':<6} {'RESOLUTION':<14} {'VIDEO CODEC':<16} {'AUDIO CODEC':<16} SIZE")
    for item in formats:
        resolution = item["resolution"] or (f"{item['height']}p" if item["height"] else (
            "audio only" if item["vcodec"] == "none" and item["acodec"] not in {None, "none"} else "unknown"
        ))
        size = item["filesize"] or item["filesize_approx"]
        label = f"{size / 1048576:.1f} MiB" if size is not None else "unknown"
        if item["filesize"] is None and item["filesize_approx"] is not None:
            label = "~" + label
        print(f"{item['format_id'] or '-':<12} {item['ext'] or '-':<6} {resolution:<14} "
              f"{item['vcodec'] or 'unknown':<16} {item['acodec'] or 'unknown':<16} {label}")
    if not formats:
        print("No downloadable formats reported")


if __name__ == "__main__":
    main()
