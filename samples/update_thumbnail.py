from _common import client, parser

if __name__ == "__main__":
    arguments = parser("Set a video's custom thumbnail from a local image file.")
    arguments.add_argument("--videoId", required=True)
    arguments.add_argument("--thumbnail", required=True, help="path to a local image, max 2 MB")
    args = arguments.parse_args()

    client(args).upload_thumbnail(args.videoId, args.thumbnail)
