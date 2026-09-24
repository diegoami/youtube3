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
    result = actions.undo_actions(client(args), log, apply=args.apply, limit=args.limit)
    what = {"like": "unlike", "playlist": "delete from the playlist", "subscribe": "unsubscribe from"}[log["action"]]
    if log["action"] == "playlist" and log.get("new_playlist"):
        what = "delete the playlist the run created:"
    print(f"{len(result['planned'])} to {what} {' '.join(result['planned'])}")
    print(f"Quota: {result['cost']} units.")
    left = len(result["over_limit"])
    if not args.apply:
        print("Dry run: nothing changed. Add --apply to do it.")
    else:
        for item_id, reason in result["failed"].items():
            print(f"Failed: {item_id} ({reason})")
        print(f"Undone: {len(result['done'])} of {len(log['done'])}.")
        left += len(result["not_done"]) + len(result["failed"])
    if left:
        # Never a silent partial undo: say what is left and how to finish.
        stopped = f" (stopped: {result['stopped']})" if result["stopped"] else ""
        raise SystemExit(f"{left} not undone{stopped}. Run the same command again later to finish.")
