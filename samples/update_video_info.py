from _common import client, parser

if __name__ == "__main__":
    arguments = parser("Change a video's title and/or description.")
    arguments.add_argument("--videoId", required=True)
    arguments.add_argument("--title")
    arguments.add_argument("--description")
    args = arguments.parse_args()
    if args.title is None and args.description is None:
        arguments.error("give --title, --description or both")

    youtube = client(args)
    video_snippet = youtube.get_video_snippet(args.videoId)
    if args.title is not None:
        video_snippet["title"] = args.title
    if args.description is not None:
        video_snippet["description"] = args.description
    youtube.update_snippet(video_id=args.videoId, video_snippet=video_snippet)
