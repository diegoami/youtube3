"""Dispatch installed youtube3 commands."""

import argparse
import runpy
import sys
from pathlib import Path

from .. import profiles
from ..auth import write_private


COMMANDS = {
    "profiles": "profiles",
    "likes": {
        "export": "export_liked_videos",
        "unlike": "unlike_videos",
        "relike": "relike_videos",
        "page": "build_liked_page",
    },
    "publish": "publish_video",
    "playlist": {
        "show": "show_files_in_playlist",
        "move": "move_videos_playlist",
        "remove": "remove_videos_playlist",
        "publish": "publish_videos_playlist",
    },
    "video": {"info": "retrieve_video_info", "check": "verify_video"},
    "subscriptions": {"list": "show_subscribed", "add": "subscribe_channel"},
}


def _parser():
    parser = argparse.ArgumentParser(
        prog="youtube3",
        description="Manage your YouTube channels, likes, playlists and videos.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("setup", help="install OAuth client secrets in the config folder")
    for name, target in COMMANDS.items():
        command = commands.add_parser(name, help=f"{name} commands")
        if isinstance(target, dict):
            subcommands = command.add_subparsers(dest="subcommand", required=True)
            for subcommand in target:
                subcommands.add_parser(subcommand, help=f"{name} {subcommand}")
    return parser


def _setup(arguments):
    if len(arguments) != 1:
        raise SystemExit("usage: youtube3 setup CLIENT_SECRETS.json")
    source = Path(arguments[0]).expanduser()
    if not source.is_file():
        raise SystemExit(f"Error: {source}: no such file")
    destination = profiles.config_dir().parent / "client_secrets.json"
    profiles.make_folder(destination.parent)
    write_private(destination, source.read_text(encoding="utf-8"))
    print(f"OAuth client secrets installed at {destination}")


def main():
    if len(sys.argv) < 2:
        _parser().print_help()
        return
    if sys.argv[1] in {"-h", "--help"}:
        _parser().print_help()
        return
    if sys.argv[1] == "setup":
        if len(sys.argv) == 3 and sys.argv[2] in {"-h", "--help"}:
            print("usage: youtube3 setup CLIENT_SECRETS.json")
            return
        _setup(sys.argv[2:])
        return
    command = sys.argv[1]
    target = COMMANDS.get(command)
    if target is None:
        _parser().error(f"argument command: invalid choice: {command!r}")
    if isinstance(target, dict):
        if len(sys.argv) < 3 or sys.argv[2] not in target:
            _parser().parse_args(sys.argv[1:])
        module = target[sys.argv[2]]
        forwarded = sys.argv[3:]
    else:
        module = target
        forwarded = sys.argv[2:]
    sys.argv = [f"youtube3 {command}"] + forwarded
    runpy.run_module(f"youtube3.cli.{module}", run_name="__main__")
