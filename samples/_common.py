"""Shared set-up for the samples: arguments, logging and the client."""

import argparse
import logging
from pathlib import Path

from youtube3 import YoutubeClient

DEFAULT_SECRETS = Path(__file__).parent / "client_secrets.json"


def parser(description):
    result = argparse.ArgumentParser(description=description)
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


def client(args):
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    return YoutubeClient(args.client_secrets, token_file=args.token_file)
