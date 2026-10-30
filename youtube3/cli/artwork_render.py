"""Render local artwork, with an offline preview by default."""

import argparse
import json
from pathlib import Path

from youtube3 import artwork


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--background", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--text", default="")
    parser.add_argument("--episode", type=int)
    parser.add_argument("--font", type=Path)
    parser.add_argument("--font-size", type=int, default=64)
    parser.add_argument("--color", default="white")
    parser.add_argument("--position", nargs=2, type=int, default=(40, 40), metavar=("X", "Y"))
    parser.add_argument("--preset", choices=artwork.PRESETS, default="video")
    parser.add_argument("--size", nargs=2, type=int, metavar=("WIDTH", "HEIGHT"))
    parser.add_argument("--fit", choices=("cover", "contain", "stretch"), default="cover")
    parser.add_argument("--config", type=Path, help="original generator's JSON/YAML configuration")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--apply", action="store_true", help="write local image files")
    args = parser.parse_args()
    try:
        if args.config:
            if args.background or args.out:
                parser.error("--config cannot be combined with --background or --out")
            plans = artwork.legacy_plans(args.config, overwrite=args.overwrite)
        else:
            if not args.background or not args.out:
                parser.error("give --background and --out, or --config")
            plans = [artwork.plan_thumbnail(args.background, args.out, text=args.text, episode=args.episode,
                                           font=args.font, font_size=args.font_size, color=args.color,
                                           position=args.position, preset=args.preset, size=args.size,
                                           fit=args.fit, overwrite=args.overwrite)]
        print(json.dumps(plans, indent=2))
        if args.apply:
            for plan in plans:
                print(f"Saved {artwork.render_plan(plan)}")
        else:
            print("Dry run: no files generated. Add --apply to render locally.")
    except (ValueError, OSError) as error:
        parser.exit(1, f"Error: {error}\n")


if __name__ == "__main__":
    main()
