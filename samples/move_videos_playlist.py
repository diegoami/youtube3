from _common import client, parser

if __name__ == "__main__":
    arguments = parser("Move positions start..end-1 of one playlist to another; a dry run unless --apply.")
    arguments.add_argument("--playlistSource", required=True)
    arguments.add_argument("--playlistTarget", required=True)
    arguments.add_argument("--start", type=int, required=True)
    arguments.add_argument("--end", type=int, required=True)
    arguments.add_argument("--apply", action="store_true", help="really move them")
    args = arguments.parse_args()

    youtube = client(args)
    source, target = args.playlistSource, args.playlistTarget
    video_ids = youtube.copy_to_playlist(source, target, args.start, args.end, apply=args.apply)
    if not args.apply:
        print(f"Would move {len(video_ids)} videos from {source} to {target}: {' '.join(video_ids)}")
        print("Dry run: nothing changed. Add --apply to do it.")
    else:
        youtube.delete_from_playlist(source, args.start, args.end)
        print(f"Moved {len(video_ids)} videos from {source} to {target}.")
