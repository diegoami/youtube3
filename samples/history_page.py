"""One command: import the newest Takeout export, build the history page, open it."""

import shutil
import subprocess
import webbrowser

from _common import channel_title, default_path
from import_history import arguments_for, import_and_check

from youtube3 import page

if __name__ == "__main__":
    arguments = arguments_for("Import the newest Takeout export, build the history page and open it.")
    arguments.add_argument("--no-open", action="store_true", help="build the page without opening it")
    args = arguments.parse_args()
    args.out = default_path(args.out, "history", ".json", args.profile)

    _, liked = import_and_check(args)
    html = default_path(None, "history", ".html", args.profile)
    likes_page = html.with_name(default_path(None, "liked", ".html", args.profile).name)
    name = channel_title(args.profile)
    path = page.build_history_page(
        args.out,
        html,
        title=f"Watch history · {name}" if name else "Watch history",
        liked={"videos": [{"video_id": video_id} for video_id in liked]} if liked else None,
        links=[("Liked videos", likes_page.name)] if likes_page.exists() else [],
    )
    print(f"Page: {path.resolve()}")
    if not args.no_open:
        # On WSL the Windows browser opens it; elsewhere the default browser.
        if shutil.which("explorer.exe"):
            subprocess.run(["explorer.exe", path.name], cwd=path.resolve().parent, check=False)
        else:
            webbrowser.open(path.resolve().as_uri())
