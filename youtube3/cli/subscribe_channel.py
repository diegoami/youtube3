from .common import client, parser


def subscribe(youtube, channel_id, apply):
    if not apply:
        return f"Dry run: would subscribe to {channel_id}. Add --apply to do it."
    youtube.subscribe_channel(channel_id)
    return f"Subscribed to {channel_id}."

if __name__ == "__main__":
    arguments = parser("Subscribe to a channel.")
    arguments.add_argument("--channelId", required=True)
    arguments.add_argument("--apply", action="store_true", help="really subscribe to the channel")
    args = arguments.parse_args()

    print(subscribe(client(args), args.channelId, args.apply))
