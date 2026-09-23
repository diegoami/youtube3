from _common import client, parser

if __name__ == "__main__":
    arguments = parser("Make every video in a playlist public; a dry run unless --apply.")
    arguments.add_argument("--playlistId", required=True)
    arguments.add_argument("--apply", action="store_true", help="really make them public")
    args = arguments.parse_args()

    youtube = client(args)
    print(f"Playlist_name: {youtube.playlist_name(args.playlistId)}")
    video_ids = [
        item["contentDetails"]["videoId"]
        for page in youtube.iterate_videos_in_playlist(args.playlistId)
        for item in page["items"]
    ]
    if not args.apply:
        print(f"Would make {len(video_ids)} videos public: {' '.join(video_ids)}")
        print("Dry run: nothing changed. Add --apply to do it.")
    else:
        for video_id in video_ids:
            youtube.update_status(video_id, "public")
        print(f"Made {len(video_ids)} videos public.")
