from pathlib import Path

from _common import client, parser

from youtube3 import actions

if __name__ == "__main__":
    arguments = parser("Undo a run of act_on_history.py from its log; a dry run unless --apply.")
    arguments.add_argument("--from", dest="log", type=Path, required=True, help="a history-like/playlist/subscribe-*.json log")
    arguments.add_argument("--limit", type=int, help="undo at most this many (default: all of the log)")
    arguments.add_argument("--apply", action="store_true", help="really undo it")
    args = arguments.parse_args()

    log = actions.load_log(args.log)
    if not log["done"]:
        raise SystemExit(f"{args.log}: nothing left to undo")
    result = actions.undo_actions(client(args), log, apply=args.apply, limit=args.limit)
    if args.apply:
        # What was undone leaves the log, so running this again carries on.
        actions.mark_undone(args.log, result)
    what = {"like": "unlike", "playlist": "delete from the playlist", "subscribe": "unsubscribe from"}[log["action"]]
    if log["action"] == "playlist" and log.get("new_playlist"):
        what = "delete the playlist the run created:"
    print(f"{len(result['planned'])} to {what} {' '.join(result['planned'])}")
    print(f"Quota: {result['cost']} units.")
    if not args.apply:
        print("Dry run: nothing changed. Add --apply to do it.")
        if result["over_limit"]:
            print(f"{len(result['over_limit'])} more are past --limit; each applied run takes the next ones.")
    else:
        for item_id, reason in result["failed"].items():
            print(f"Failed: {item_id} ({reason})")
        print(f"Undone: {len(result['done'])} of {len(log['done'])}.")
        left = len(result["over_limit"]) + len(result["not_done"]) + len(result["failed"])
        if left:
            # Never a silent partial undo. What was undone has left the log,
            # so the same command carries on with the rest.
            stopped = f" (stopped: {result['stopped']})" if result["stopped"] else ""
            raise SystemExit(f"{left} not undone yet{stopped}. Run the same command again to carry on.")
