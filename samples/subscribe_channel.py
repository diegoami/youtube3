from _common import client, parser

if __name__ == "__main__":
    arguments = parser("Subscribe to a channel.")
    arguments.add_argument("--channelId", required=True)
    args = arguments.parse_args()

    client(args).subscribe_channel(args.channelId)
