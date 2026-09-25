from pathlib import Path

from _common import client, default_path, parser

from youtube3 import likes

if __name__ == "__main__":
    arguments = parser("Export your liked videos to a JSON file, newest like first.")
    arguments.add_argument("--out", type=Path, help="default: liked.json, or liked-<profile>.json")
    args = arguments.parse_args()
    args.out = default_path(args.out, "liked", ".json", args.profile)

    change = likes.export_liked_videos(client(args), args.out)
    print(f"{change['count']} liked videos saved to {args.out}")
    print(f"Since the previous export: {len(change['added'])} added, {len(change['removed'])} removed")
    for video_id in change["removed"]:
        print(f"  no longer liked: {video_id}")
