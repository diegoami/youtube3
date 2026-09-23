from _common import client, parser

if __name__ == "__main__":
    arguments = parser("List the videos in a playlist.")
    arguments.add_argument("--playlistId", required=True)
    args = arguments.parse_args()

    youtube = client(args)
    print(f"Playlist_name: {youtube.playlist_name(args.playlistId)}")
    for video_items in youtube.iterate_videos_in_playlist(args.playlistId):
        for item in video_items["items"]:
            print(item["contentDetails"]["videoId"], item["snippet"]["title"])
