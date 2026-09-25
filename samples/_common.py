"""Shared set-up for the samples: arguments, logging, the client and file names."""

import argparse
import logging
from pathlib import Path

from youtube3 import YoutubeClient, profiles

DEFAULT_SECRETS = Path(__file__).parent / "client_secrets.json"


def parser(description):
    result = argparse.ArgumentParser(description=description)
    add_profile(result)
    result.add_argument(
        "--client-secrets",
        type=Path,
        default=DEFAULT_SECRETS,
        help="OAuth client secrets from the Google Cloud console (default: %(default)s)",
    )
    result.add_argument(
        "--token-file",
        type=Path,
        help="where the login is saved (default: token.json next to the client secrets)",
    )
    return result


def add_profile(arguments):
    arguments.add_argument("--profile", help="the channel to act on, by profile name (see profiles.py)")


def client(args, quiet=False):
    """Log in, and say which channel this run acts on before it does anything."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        youtube = YoutubeClient(args.client_secrets, token_file=args.token_file, profile=args.profile)
        channel = youtube.signed_in_channel()
    except (profiles.ProfileError, ValueError) as error:
        raise SystemExit(f"Error: {error}") from None
    if not quiet:
        print(f"Signed in as {channel['title']} ({channel['id']})")
    return youtube


def default_path(value, stem, suffix, profile):
    """The path given, or <stem>.<suffix> / <stem>-<profile>.<suffix>."""
    return Path(value) if value else Path(profiles.output_name(stem, suffix, profile))


def channel_title(profile):
    """The profile's channel, from what it saved (no API call), for page titles."""
    try:
        saved = profiles.saved_channel(profile) if profile else None
    except profiles.ProfileError:
        return None
    return saved["title"] if saved else None
