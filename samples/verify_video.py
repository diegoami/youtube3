from _common import client, parser

if __name__ == "__main__":
    arguments = parser("Say whether a video can be watched in a country.")
    arguments.add_argument("--videoId", required=True)
    arguments.add_argument("--country", default="DE")
    args = arguments.parse_args()

    print(client(args).verify_video(args.videoId, country=args.country))
