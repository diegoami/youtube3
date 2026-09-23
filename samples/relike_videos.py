from pathlib import Path

from _common import client, parser
from _rating import run

from youtube3 import likes

if __name__ == "__main__":
    arguments = parser("Like again the videos an unlike run logged; a dry run unless --apply.")
    arguments.add_argument("--from", dest="log", type=Path, required=True, help="an unliked-*.json log")
    arguments.add_argument("--limit", type=int, default=likes.DEFAULT_LIMIT)
    arguments.add_argument("--apply", action="store_true", help="really like them again")
    args = arguments.parse_args()

    log = likes.load_export(args.log)
    if log.get("rating") != "none":
        arguments.error(f"{args.log} is not the log of an unlike run")
    run(client(args), log["videos"], "like", args.apply, args.limit, args.log.parent)
    print("Run export_liked_videos.py to refresh the export.")
