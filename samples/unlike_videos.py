from pathlib import Path

from _common import client, default_path, parser
from _rating import run

from youtube3 import likes

if __name__ == "__main__":
    arguments = parser("Unlike the liked videos an export selects; a dry run unless --apply.")
    arguments.add_argument("--from", dest="export", type=Path, help="default: liked.json, or liked-<profile>.json")
    arguments.add_argument("--channel", help="a channel id, or a channel title in any case")
    arguments.add_argument("--liked-before", help="YYYY-MM-DD: liked before that day")
    arguments.add_argument("--liked-after", help="YYYY-MM-DD: liked on that day or later")
    arguments.add_argument("--ids", help="comma-separated video ids")
    arguments.add_argument("--unavailable", action="store_true", help="only deleted or private videos")
    arguments.add_argument("--limit", type=int, default=likes.DEFAULT_LIMIT)
    arguments.add_argument("--apply", action="store_true", help="really unlike them")
    args = arguments.parse_args()
    args.export = default_path(args.export, "liked", ".json", args.profile)
    if not any([args.channel, args.liked_before, args.liked_after, args.ids, args.unavailable]):
        arguments.error("give at least one of --channel, --liked-before, --liked-after, --ids, --unavailable")

    videos = likes.select(
        likes.load_export(args.export)["videos"],
        channel=args.channel,
        liked_before=args.liked_before,
        liked_after=args.liked_after,
        ids=args.ids.split(",") if args.ids else None,
        unavailable=True if args.unavailable else None,
    )
    youtube = client(args)
    done = run(youtube, videos, "none", args.apply, args.limit, args.export.parent)
    if done:
        likes.remove_from_export(args.export, [v["video_id"] for v in done])
        print(f"Removed them from {args.export}.")
