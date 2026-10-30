"""Set a playlist cover from a file or a manifest's separate cover entry."""

import json
from pathlib import Path

from .common import parser, client
from youtube3 import playlist_cover, playlist_artwork


def main():
    arguments = parser(__doc__)
    arguments.add_argument("playlist_id")
    source = arguments.add_mutually_exclusive_group(required=True)
    source.add_argument("--image", type=Path)
    source.add_argument("--manifest", type=Path)
    arguments.add_argument("--apply", action="store_true")
    args = arguments.parse_args()
    try:
        image = args.image
        if args.manifest:
            manifest = playlist_artwork.load_manifest(args.manifest)
            if manifest["playlist_id"] != args.playlist_id:
                arguments.error("manifest belongs to another playlist")
            image = manifest["cover"]["render"]["output"]
        youtube = client(args)
        plan = playlist_cover.plan_playlist_cover(youtube, args.playlist_id, image)
        print(json.dumps(plan, indent=2))
        if args.apply:
            response = playlist_cover.apply_playlist_cover(youtube, plan)
            print(f"Applied {plan['action']} to {args.playlist_id}; image ID: {response.get('id', 'not returned')}")
        else:
            print("Dry run: no playlist cover changed. Add --apply.")
    except (ValueError, OSError) as error:
        arguments.exit(1, f"Error: {error}\n")


if __name__ == "__main__":
    main()
