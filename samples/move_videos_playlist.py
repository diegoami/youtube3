from _common import client, parser

if __name__ == "__main__":
    arguments = parser("Move positions start..end-1 of one playlist to another.")
    arguments.add_argument("--playlistSource", required=True)
    arguments.add_argument("--playlistTarget", required=True)
    arguments.add_argument("--start", type=int, required=True)
    arguments.add_argument("--end", type=int, required=True)
    args = arguments.parse_args()

    youtube = client(args)
    youtube.copy_to_playlist(args.playlistSource, args.playlistTarget, args.start, args.end)
    youtube.delete_from_playlist(args.playlistSource, args.start, args.end)
