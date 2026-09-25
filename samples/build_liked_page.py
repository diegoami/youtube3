import argparse
from pathlib import Path

from _common import add_profile, channel_title, default_path

from youtube3 import page

if __name__ == "__main__":
    arguments = argparse.ArgumentParser(description="Build a web page of your liked videos from an export.")
    add_profile(arguments)
    arguments.add_argument("--from", dest="export", type=Path, help="default: liked.json, or liked-<profile>.json")
    arguments.add_argument("--out", type=Path, help="default: liked.html, or liked-<profile>.html")
    arguments.add_argument("--title", help="default: Liked videos, with the channel's name for a profile")
    args = arguments.parse_args()
    args.export = default_path(args.export, "liked", ".json", args.profile)
    args.out = default_path(args.out, "liked", ".html", args.profile)
    name = channel_title(args.profile)
    args.title = args.title or (f"Liked videos · {name}" if name else "Liked videos")

    path = page.build_page(args.export, args.out, title=args.title)
    print(f"Open {path.resolve().as_uri()} in a browser.")
