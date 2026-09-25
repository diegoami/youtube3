import argparse
from pathlib import Path

from _common import add_profile, channel_title, default_path

from youtube3 import page

if __name__ == "__main__":
    arguments = argparse.ArgumentParser(description="Build a web page of your watch history from history.json.")
    add_profile(arguments)
    arguments.add_argument("--from", dest="history", type=Path, help="default: history.json, or history-<profile>.json")
    arguments.add_argument("--likes", type=Path, help="a likes export, to mark the videos you also liked")
    arguments.add_argument("--out", type=Path, help="default: history.html, or history-<profile>.html")
    arguments.add_argument("--title", help="default: Watch history, with the channel's name for a profile")
    args = arguments.parse_args()
    args.history = default_path(args.history, "history", ".json", args.profile)
    args.out = default_path(args.out, "history", ".html", args.profile)
    name = channel_title(args.profile)
    args.title = args.title or (f"Watch history · {name}" if name else "Watch history")

    likes_page = args.out.with_name(default_path(None, "liked", ".html", args.profile).name)
    links = [("Liked videos", likes_page.name)] if likes_page.exists() else []
    path = page.build_history_page(args.history, args.out, title=args.title, liked=args.likes, links=links)
    print(f"Open {path.resolve().as_uri()} in a browser.")
