"""Retry only the failed IDs saved in a playlist download report."""

import argparse
from pathlib import Path

from youtube3.download import DownloadError
from youtube3.download_batch import download_batch, retry_plan


def main():
    parser = argparse.ArgumentParser(prog="youtube3 download retry",
                                     description="Preview failed report entries offline; --apply retries them.")
    parser.add_argument("source", type=Path, help="previous download report JSON")
    parser.add_argument("--report", type=Path, help="save retry results to a NEW JSON file (requires --apply)")
    parser.add_argument("--continue-on-error", action="store_true", help="attempt every failed entry")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="retry the displayed failed selection")
    mode.add_argument("--dry-run", action="store_true", help="offline preview only (default)")
    args = parser.parse_args()
    if args.report is not None and not args.apply:
        parser.error("--report requires --apply")
    try:
        plan, quality = retry_plan(args.source)
        print(f"Playlist: {plan.title}\nOutput: {plan.output}\nArchive: {plan.archive}")
        print(f"Media: {plan.media.description(quality)}")
        for entry in plan.entries:
            print(f"{entry.position:05d} [retry] {entry.video_id} {entry.title}")
        print(f"{len(plan.entries)} failed entries selected; completed IDs will be skipped using the archive")
        if args.apply:
            result = download_batch(plan, quality=quality, continue_on_error=args.continue_on_error, report=args.report)
            print(result.summary())
            if result.failed:
                parser.exit(1, "Some downloads failed.\n")
        else:
            print("Preview only: no network access or files written. Add --apply to retry.")
    except (ValueError, DownloadError) as error:
        parser.exit(1, f"Error: {error}\n")


if __name__ == "__main__":
    main()
