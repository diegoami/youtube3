"""Profiles: one saved login per channel (brand account)."""

import argparse
from pathlib import Path

from _common import DEFAULT_SECRETS

from youtube3 import YoutubeClient, profiles

if __name__ == "__main__":
    arguments = argparse.ArgumentParser(description="Manage one saved login per channel (brand account).")
    arguments.add_argument("--client-secrets", type=Path, default=DEFAULT_SECRETS)
    commands = arguments.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="each profile and its channel")
    add = commands.add_parser("add", help="log in (the browser asks which account or brand) and save it")
    add.add_argument("name")
    whoami = commands.add_parser("whoami", help="check a profile's login against its channel")
    whoami.add_argument("name")
    adopt = commands.add_parser("adopt", help="make an existing token a profile, without logging in again")
    adopt.add_argument("name")
    adopt.add_argument("--token-file", type=Path, default=DEFAULT_SECRETS.parent / "token.json")
    args = arguments.parse_args()

    try:
        if args.command == "list":
            found = profiles.list_profiles()
            print(f"Profiles in {profiles.config_dir()}:" if found else f"No profile yet in {profiles.config_dir()}.")
            for profile in found:
                channel = f"{profile['title']} ({profile['id']})" if profile["id"] else "not used yet"
                print(f"  {profile['name']:20} {channel}")
        elif args.command == "adopt":
            print(f"Saved as {profiles.adopt(args.name, args.token_file)}; the original is kept.")
            channel = YoutubeClient(args.client_secrets, profile=args.name).signed_in_channel()
            print(f"{args.name}: {channel['title']} ({channel['id']})")
        else:
            if args.command == "add" and profiles.token_path(args.name).exists():
                raise profiles.ProfileError(f"profile {args.name!r} already exists")
            channel = YoutubeClient(args.client_secrets, profile=args.name).signed_in_channel()
            print(f"{args.name}: {channel['title']} ({channel['id']})")
    except profiles.ProfileError as error:
        raise SystemExit(f"Error: {error}") from None
