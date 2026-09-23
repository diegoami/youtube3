from _common import client, parser

if __name__ == "__main__":
    arguments = parser("Remove positions start..end-1 from a playlist.")
    arguments.add_argument("--playlistSource", required=True)
    arguments.add_argument("--start", type=int, required=True)
    arguments.add_argument("--end", type=int, required=True)
    args = arguments.parse_args()

    client(args).delete_from_playlist(args.playlistSource, args.start, args.end)
