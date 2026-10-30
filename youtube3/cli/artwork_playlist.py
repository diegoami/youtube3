"""Plan playlist artwork online or from a snapshot; render a saved mapping offline."""

import json
from pathlib import Path

from .common import parser, client
from youtube3 import playlist_artwork


def main():
    arguments = parser(__doc__)
    source = arguments.add_mutually_exclusive_group(required=True)
    source.add_argument("--playlist-id", help="read metadata online using the selected profile")
    source.add_argument("--snapshot", type=Path, help="offline JSON playlist snapshot")
    source.add_argument("--plan", type=Path, help="saved manifest; no online lookup")
    arguments.add_argument("--background", type=Path)
    arguments.add_argument("--output-dir", type=Path)
    arguments.add_argument("--manifest", type=Path, help="save fixed mapping when --apply is given")
    arguments.add_argument("--save-plan", type=Path, help="explicitly save the plan without rendering")
    arguments.add_argument("--start", type=int, default=1)
    arguments.add_argument("--end", type=int)
    arguments.add_argument("--number-offset", type=int, default=0)
    arguments.add_argument("--text", default="Episode {episode}")
    arguments.add_argument("--cover-text")
    arguments.add_argument("--font", type=Path)
    arguments.add_argument("--font-size", type=int, default=64)
    arguments.add_argument("--color", default="white")
    arguments.add_argument("--position", type=int, nargs=2, default=(40, 40))
    arguments.add_argument("--overwrite", action="store_true")
    arguments.add_argument("--apply", action="store_true", help="render images locally; no account writes")
    args = arguments.parse_args()
    try:
        if args.plan:
            manifest = playlist_artwork.load_manifest(args.plan)
        else:
            if args.background is None or args.output_dir is None:
                arguments.error("--background and --output-dir are required for a new plan")
            if args.snapshot:
                print("Offline snapshot: no account calls.")
                snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
            else:
                print("Online metadata read: no account writes.")
                snapshot = playlist_artwork.playlist_snapshot(client(args), args.playlist_id)
            manifest = playlist_artwork.plan_playlist_artwork(
                snapshot, args.background, args.output_dir, start=args.start, end=args.end,
                number_offset=args.number_offset, text=args.text, cover_text=args.cover_text,
                font=args.font, font_size=args.font_size, color=args.color, position=args.position,
                overwrite=args.overwrite)
        print(json.dumps(manifest, indent=2))
        if args.save_plan:
            playlist_artwork.save_manifest(manifest, args.save_plan, overwrite=args.overwrite)
        if args.apply:
            path = args.manifest or args.plan
            if path is None:
                path = args.output_dir / "artwork.json"
            # Persist the mapping before rendering; never silently lose the IDs.
            playlist_artwork.save_manifest(manifest, path, overwrite=args.overwrite or path == args.plan)
            playlist_artwork.render_playlist_artwork(manifest, overwrite=args.overwrite)
            print(f"Rendered images; mapping saved to {path}")
        else:
            print("Dry run: no images generated or account writes. Add --apply to render locally.")
    except (ValueError, OSError, KeyError, TypeError) as error:
        arguments.exit(1, f"Error: {error}\n")


if __name__ == "__main__":
    main()
