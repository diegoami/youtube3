import argparse
from pathlib import Path

from youtube3 import page

if __name__ == "__main__":
    arguments = argparse.ArgumentParser(description="Build a web page of your liked videos from an export.")
    arguments.add_argument("--from", dest="export", type=Path, default=Path("liked.json"))
    arguments.add_argument("--out", type=Path, default=Path("liked.html"))
    arguments.add_argument("--title", default="Liked videos")
    args = arguments.parse_args()

    history_page = args.out.with_name("history.html")
    links = [("Watch history", history_page.name)] if history_page.exists() else []
    path = page.build_page(args.export, args.out, title=args.title, links=links)
    print(f"Open {path.resolve().as_uri()} in a browser.")
