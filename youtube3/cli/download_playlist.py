"""Preview a public playlist, then explicitly apply the selected downloads."""

import argparse
from pathlib import Path

from youtube3.download import DownloadError, download_playlist, preview_playlist
from youtube3.download_batch import download_batch
from youtube3.cli.download_options import add_media_arguments, media_options, positive_height


def main():
    parser = argparse.ArgumentParser(
        prog="youtube3 download playlist",
        description="Preview public playlist downloads; --apply downloads the listed selection. No Google login.",
    )
    parser.add_argument("playlist", help="public playlist ID or HTTPS YouTube playlist/watch URL with list=ID")
    parser.add_argument("--output", type=Path, default=Path("downloads"), help="output folder (default: downloads)")
    parser.add_argument("--quality", type=positive_height, help="maximum video height in pixels, e.g. 720 or 1080")
    parser.add_argument("--start", type=int, default=1, help="first playlist position (1-based, inclusive)")
    parser.add_argument("--end", type=int, help="last playlist position (inclusive; default: to the end)")
    parser.add_argument("--archive", type=Path, help="completed-ID archive (default: in the output folder)")
    parser.add_argument("--report", type=Path, help="save results to a NEW JSON file (requires --apply)")
    parser.add_argument("--continue-on-error", action="store_true", help="attempt remaining entries after a failure")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="download after printing the selection")
    mode.add_argument("--dry-run", action="store_true", help="preview only (default); reads playlist metadata online")
    add_media_arguments(parser)
    args = parser.parse_args()
    media = media_options(args, parser)
    if args.report is not None and not args.apply:
        parser.error("--report requires --apply")
    try:
        plan = preview_playlist(args.playlist, args.output, start=args.start, end=args.end, archive=args.archive, media=media)
        print(f"Playlist: {plan.title}\nOutput: {plan.output}\nArchive: {plan.archive}")
        print(f"Media: {media.description(args.quality)}")
        for entry in plan.entries:
            action = f"skip: {entry.skip_reason}" if entry.skip_reason else "download"
            print(f"{entry.position:05d} [{action}] {entry.video_id or '-'} {entry.title}")
        pending = sum(entry.skip_reason is None for entry in plan.entries)
        print(f"{len(plan.entries)} selected; {pending} to download; {len(plan.entries) - pending} skipped")
        if args.apply:
            if args.report is not None or args.continue_on_error:
                result = download_batch(plan, quality=args.quality, continue_on_error=args.continue_on_error,
                                        report=args.report)
                print(result.summary())
                if result.failed:
                    parser.exit(1, "Some downloads failed.\n")
            else:
                download_playlist(plan, quality=args.quality)
            print("Playlist download complete")
        else:
            print("Preview only: no files written. Add --apply to download. Media availability is not verified.")
    except (ValueError, DownloadError) as error:
        parser.exit(1, f"Error: {error}\n")


if __name__ == "__main__":
    main()
