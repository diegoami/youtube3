import argparse
from pathlib import Path

from youtube3 import page

if __name__ == "__main__":
    arguments = argparse.ArgumentParser(description="Build a web page of your watch history from history.json.")
    arguments.add_argument("--from", dest="history", type=Path, default=Path("history.json"))
    arguments.add_argument("--likes", type=Path, help="a likes export, to mark the videos you also liked")
    arguments.add_argument("--out", type=Path, default=Path("history.html"))
    arguments.add_argument("--title", default="Watch history")
    args = arguments.parse_args()

    likes_page = args.out.with_name("liked.html")
    links = [("Liked videos", likes_page.name)] if likes_page.exists() else []
    path = page.build_history_page(args.history, args.out, title=args.title, liked=args.likes, links=links)
    print(f"Open {path.resolve().as_uri()} in a browser.")
