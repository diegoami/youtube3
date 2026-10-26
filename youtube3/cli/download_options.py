"""Arguments shared by download commands, without OAuth setup."""

import argparse
from fractions import Fraction
import re

from youtube3.download import MediaOptions, TransferOptions


def rate_limit(value):
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)([KMG](?:i?B)?|B)?", value.strip(), re.IGNORECASE)
    if match is not None:
        unit = (match[2] or "B")[0].upper()
        rate = int(Fraction(match[1]) * 1024 ** {"B": 0, "K": 1, "M": 2, "G": 3}[unit])
        if rate > 0:
            return rate
    raise argparse.ArgumentTypeError("rate must be positive bytes/s, e.g. 500K, 1.5M or 2097152")


def retry_count(value):
    count = int(value)
    if count < 0:
        raise argparse.ArgumentTypeError("retry count must be a nonnegative integer (0 disables retries)")
    return count


def add_transfer_arguments(parser):
    parser.add_argument("--limit-rate", type=rate_limit, help="media bandwidth cap in bytes/s, e.g. 500K or 2M")
    parser.add_argument("--retries", type=retry_count, help="HTTP retries per media transfer (0 disables retries)")
    parser.add_argument("--fragment-retries", type=retry_count, help="retries per media fragment (0 disables retries)")


def transfer_options(args):
    return TransferOptions(limit_rate=args.limit_rate, retries=args.retries, fragment_retries=args.fragment_retries)


def positive_height(value):
    height = int(value)
    if height <= 0:
        raise argparse.ArgumentTypeError("quality must be a positive height in pixels")
    return height


def add_media_arguments(parser):
    parser.add_argument("--audio-only", action="store_true", help="download native audio without video")
    parser.add_argument("--audio-format", choices=["mp3", "m4a", "opus", "flac", "wav"],
                        help="convert audio (requires --audio-only, FFmpeg and ffprobe)")
    parser.add_argument("--subtitles", help="comma-separated subtitle languages, e.g. en,de")
    parser.add_argument("--auto-subtitles", action="store_true", help="also allow automatic captions for --subtitles")
    parser.add_argument("--write-metadata", action="store_true", help="save an .info.json sidecar")
    parser.add_argument("--write-thumbnail", action="store_true", help="save a thumbnail sidecar")


def media_options(args, parser):
    try:
        media = MediaOptions(
            audio_only=args.audio_only, audio_format=args.audio_format,
            subtitles=tuple(language.strip() for language in args.subtitles.split(",")) if args.subtitles is not None else (),
            auto_subtitles=args.auto_subtitles, write_metadata=args.write_metadata, write_thumbnail=args.write_thumbnail,
        )
        if media.audio_only and args.quality is not None:
            raise ValueError("--quality cannot be combined with --audio-only")
        return media
    except ValueError as error:
        parser.error(str(error))
