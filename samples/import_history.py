from pathlib import Path

from _common import client, default_path, parser

from youtube3 import history, likes


def import_and_check(args):
    """Import the export (the newest one in Downloads by default); with a profile,
    warn when it does not look like that channel's history. Prints counts only."""
    source = args.takeout or history.find_latest_takeout()
    if source is None:
        raise SystemExit("Error: no takeout-*.zip with a watch history in Downloads; give --takeout")
    print(f"Export: {source}")
    try:
        summary = history.import_history(
            source, args.out, include_ads=args.include_ads, include_music=args.include_music
        )
    except history.HistoryError as error:
        raise SystemExit(f"Error: {error}") from None
    print(f"Saved to {args.out}")
    print(f"Watches: {summary['count']} of {summary['videos']} different videos, from {summary['first']} to {summary['last']}")
    print(f"Watched more than once: {summary['rewatched']} videos; removed since: {summary['removed']}")
    print(f"Left out: {summary['left_out']['ads']} ads, {summary['left_out']['music']} YouTube Music entries")
    liked = None
    if args.profile:
        youtube = client(args)
        liked = {video["video_id"] for video in youtube.iterate_liked_videos() if video["available"]}
        check = history.likes_overlap(likes.load_export(args.out)["videos"], liked)
        print(f"{check['found']} of the channel's {check['liked']} likes are among these watches.")
        if check["another_account"]:
            print(
                "Warning: this looks like another account's history. Takeout exports the account "
                "selected at its top right: switch to this channel's account there and export again."
            )
    return summary, liked


def arguments_for(description):
    arguments = parser(description)
    arguments.add_argument("--takeout", type=Path, help="the Takeout zip or folder (default: the newest in Downloads)")
    arguments.add_argument("--out", type=Path, help="default: history.json, or history-<profile>.json")
    arguments.add_argument("--include-ads", action="store_true", help='keep entries marked "From Google Ads"')
    arguments.add_argument("--include-music", action="store_true", help="keep YouTube Music entries")
    return arguments


if __name__ == "__main__":
    args = arguments_for("Import your watch history from a Google Takeout export.").parse_args()
    args.out = default_path(args.out, "history", ".json", args.profile)
    import_and_check(args)
