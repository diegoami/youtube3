from pathlib import Path

from _common import client, parser

from youtube3 import actions, history, likes


def show(items, key, verb, result):
    shown = {item[key]: item for item in items}
    for item_id in result["planned"]:
        item = shown[item_id]
        if key == "video_id":
            print(f"  {(item['last_watched'] or '')[:10]}  {item_id}  x{item['views']}  {item['channel_title'] or '-'}  {item['title']}")
        else:
            print(f"  {item['views']:>5} watches  {item_id}  {item['channel_title']}")
    print(f"{len(result['planned'])} to {verb}; {len(result['skipped'])} skipped ({', '.join(sorted(set(result['skipped'].values()))) or 'none'}).")
    print(f"Quota: {result['cost']} of {likes.DAILY_QUOTA} units a day to write, plus {result.get('read_cost', 0)} spent reading.")
    if result["over_limit"]:
        print(f"{len(result['over_limit'])} more are over --limit; run again tomorrow for them.")


if __name__ == "__main__":
    arguments = parser("Like, collect into a playlist, or subscribe from your watch history; a dry run unless --apply.")
    arguments.add_argument("action", choices=["like", "playlist", "subscribe"])
    arguments.add_argument("--from", dest="history", type=Path, default=Path("history.json"))
    arguments.add_argument("--channel", help="a channel id, or a channel title in any case")
    arguments.add_argument("--watched-after", help="YYYY-MM-DD: last watched on that day or later")
    arguments.add_argument("--watched-before", help="YYYY-MM-DD: last watched before that day")
    arguments.add_argument("--min-views", type=int, help="like/playlist: a video watched at least this often; subscribe: a channel (default 3)")
    arguments.add_argument("--ids", help="comma-separated video ids")
    target = arguments.add_mutually_exclusive_group()
    target.add_argument("--playlist", help="playlist: the id of an existing playlist")
    target.add_argument("--new-playlist", help="playlist: the title of a new one (private unless --privacy)")
    arguments.add_argument("--privacy", choices=actions.PLAYLIST_PRIVACY, default="private")
    arguments.add_argument("--top", type=int, default=10, help="subscribe: at most this many channels")
    arguments.add_argument("--limit", type=int, default=likes.DEFAULT_LIMIT)
    arguments.add_argument("--apply", action="store_true", help="really do it")
    args = arguments.parse_args()

    records = likes.load_export(args.history)["videos"]
    criteria = dict(
        channel=args.channel,
        watched_after=args.watched_after,
        watched_before=args.watched_before,
        min_views=args.min_views,
        ids=args.ids.split(",") if args.ids else None,
    )
    if args.action in ("like", "playlist") and not any(criteria.values()):
        arguments.error("give at least one of --channel, --watched-after, --watched-before, --min-views, --ids")
    if args.action == "playlist" and not (args.playlist or args.new_playlist):
        arguments.error("playlist needs --playlist ID or --new-playlist TITLE")

    youtube = client(args)
    if args.action == "subscribe":
        # For channels, --min-views counts the channel's watches, not each video's.
        selected = history.select_watched(records, **{**criteria, "min_views": None})
        watched = [r for r in records if r["video_id"] in {v["video_id"] for v in selected}]
        items = history.top_channels(watched, min_views=args.min_views or 3)[: args.top]
        key = "channel_id"
        result = actions.subscribe_to(youtube, items, apply=args.apply, limit=args.limit)
    else:
        items, key = history.select_watched(records, **criteria), "video_id"
        if args.action == "like":
            result = actions.like_watched(youtube, items, apply=args.apply, limit=args.limit)
        else:
            result = actions.add_to_playlist(
                youtube, items, playlist_id=args.playlist, new_title=args.new_playlist,
                privacy=args.privacy, apply=args.apply, limit=args.limit,
            )
    show(items, key, {"like": "like", "playlist": "add", "subscribe": "subscribe to"}[args.action], result)
    if not args.apply:
        print("Dry run: nothing changed. Add --apply to do it.")
    else:
        for item_id, reason in result["failed"].items():
            print(f"Failed: {item_id} ({reason})")
        if result["stopped"]:
            print(f"Stopped ({result['stopped']}): {len(result['not_done'])} not done; run again later.")
        if result["done"]:
            log = actions.write_action_log(args.history.parent, args.action, items, result)
            print(f"Done: {len(result['done'])}. Undo with: python samples/undo_history_actions.py --from {log}")
