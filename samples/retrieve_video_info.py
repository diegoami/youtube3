from _common import client, parser

if __name__ == "__main__":
    arguments = parser("Print what the API returns for a video.")
    arguments.add_argument("--videoId", required=True)
    args = arguments.parse_args()

    youtube = client(args)
    print(youtube.get_video(args.videoId))
    print(youtube.get_video_snippet(args.videoId))
    print(youtube.get_channel_id(args.videoId))
    print(youtube.get_video_content_details(args.videoId))
