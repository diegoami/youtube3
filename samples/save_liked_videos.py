import json
from pathlib import Path

from _common import client, parser


def update_liked_files(youtube, max_count, work_dir):
    liked = {}
    for videos in youtube.iterate_videos_in_playlist(youtube.liked_channel(), max_count):
        for item in videos["items"]:
            print(item["contentDetails"]["videoId"], item["snippet"]["title"])
            liked[item["contentDetails"]["videoId"]] = item["snippet"]["title"]
    with open(work_dir / "liked.json", "w", encoding="utf-8") as f:
        json.dump(liked, f, ensure_ascii=False)


if __name__ == "__main__":
    arguments = parser("Save the liked videos, id and title, to <workDir>/liked.json.")
    arguments.add_argument("--workDir", type=Path, default=Path("test"))
    arguments.add_argument("--maxCount", type=int, help="at most this many pages of 50")
    args = arguments.parse_args()

    youtube = client(args)
    args.workDir.mkdir(parents=True, exist_ok=True)
    print(f"Saving to directory: {args.workDir}")
    update_liked_files(youtube=youtube, max_count=args.maxCount, work_dir=args.workDir)
