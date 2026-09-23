from pathlib import Path

from _common import client, parser

from youtube3 import likes

if __name__ == "__main__":
    arguments = parser("Export your liked videos to a JSON file, newest like first.")
    arguments.add_argument("--out", type=Path, default=Path("liked.json"))
    args = arguments.parse_args()

    change = likes.export_liked_videos(client(args), args.out)
    print(f"{change['count']} liked videos saved to {args.out}")
    print(f"Since the previous export: {len(change['added'])} added, {len(change['removed'])} removed")
    for video_id in change["removed"]:
        print(f"  no longer liked: {video_id}")
