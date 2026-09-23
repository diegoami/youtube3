from _common import client, parser

if __name__ == "__main__":
    arguments = parser("Remove positions start..end-1 from a playlist; a dry run unless --apply.")
    arguments.add_argument("--playlistSource", required=True)
    arguments.add_argument("--start", type=int, required=True)
    arguments.add_argument("--end", type=int, required=True)
    arguments.add_argument("--apply", action="store_true", help="really remove them")
    args = arguments.parse_args()

    source = args.playlistSource
    video_ids = client(args).delete_from_playlist(source, args.start, args.end, apply=args.apply)
    if args.apply:
        print(f"Removed {len(video_ids)} videos from {source}.")
    else:
        print(f"Would remove {len(video_ids)} videos from {source}: {' '.join(video_ids)}")
        print("Dry run: nothing changed. Add --apply to do it.")
