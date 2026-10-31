"""Create an empty playlist, private by default, with an explicit apply option."""

import json

from googleapiclient.errors import HttpError

from .common import client, parser


def main():
    arguments = parser(__doc__)
    arguments.add_argument("title")
    arguments.add_argument("--description", default="")
    arguments.add_argument("--privacy", choices=("private", "unlisted", "public"), default="private")
    arguments.add_argument("--apply", action="store_true")
    args = arguments.parse_args()
    try:
        youtube = client(args)
        result = youtube.create_playlist(args.title, description=args.description,
                                         privacy=args.privacy, apply=args.apply)
        print(json.dumps(result, indent=2))
        if args.apply:
            playlist_id = result["response"].get("id")
            if not playlist_id:
                arguments.exit(1, "Error: creation returned no ID; inspect the channel before trying again.\n")
            print(f"Playlist ID: {playlist_id}")
            print(f"URL: https://www.youtube.com/playlist?list={playlist_id}")
        else:
            print("Dry run: no playlist created. Add --apply.")
    except ValueError as error:
        arguments.exit(1, f"Error: {error}\n")
    except (HttpError, OSError):
        arguments.exit(1, "Error: request failed; creation may have succeeded. Inspect the channel before trying again.\n")


if __name__ == "__main__":
    main()
