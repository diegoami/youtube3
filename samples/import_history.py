import argparse
from pathlib import Path

from youtube3 import history

if __name__ == "__main__":
    arguments = argparse.ArgumentParser(description="Import your watch history from a Google Takeout export.")
    arguments.add_argument("--takeout", type=Path, required=True, help="the Takeout zip as downloaded, or its unpacked folder")
    arguments.add_argument("--out", type=Path, default=Path("history.json"))
    arguments.add_argument("--include-ads", action="store_true", help='keep entries marked "From Google Ads"')
    arguments.add_argument("--include-music", action="store_true", help="keep YouTube Music entries")
    args = arguments.parse_args()

    try:
        summary = history.import_history(
            args.takeout, args.out, include_ads=args.include_ads, include_music=args.include_music
        )
    except history.HistoryError as error:
        raise SystemExit(f"Error: {error}") from None
    # Counts only: safe to share, no title or URL.
    print(f"Saved to {args.out}")
    print(f"Watches: {summary['count']} of {summary['videos']} different videos, from {summary['first']} to {summary['last']}")
    print(f"Watched more than once: {summary['rewatched']} videos; removed since: {summary['removed']}")
    print(f"Channels: {len(summary['top_channels'])} (up to {history.TOP_CHANNELS} counted)")
    print(f"Left out: {summary['left_out']['ads']} ads, {summary['left_out']['music']} YouTube Music entries")
