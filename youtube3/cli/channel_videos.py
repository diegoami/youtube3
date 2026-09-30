from pathlib import Path

from .common import client, default_path, parser

from youtube3 import channel

if __name__ == "__main__":
    arguments = parser("List every video uploaded to your channel, newest first.")
    arguments.add_argument("--out", type=Path, help="default: channel.json, or channel-<profile>.json")
    args = arguments.parse_args()
    args.out = default_path(args.out, "channel", ".json", args.profile)

    videos = list(client(args).iterate_channel_videos())
    for video in videos:
        views = "?" if video["views"] is None else video["views"]
        print(
            f"{video['video_id']}  {video['published_at']}  {video['privacy'] or '?'}  "
            f"{views}  {video['duration'] or '?'}  {video['title']}"
        )
    print(f"{channel.write_export(args.out, videos)} videos saved to {args.out}")
