"""Arguments shared by download commands, without OAuth setup."""

import argparse
from fractions import Fraction
import re

from youtube3.download import AccessOptions, MediaOptions, TransferOptions


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
    parser.add_argument("--sleep-interval", type=retry_count, default=5,
                        help="seconds between video extraction attempts (default: 5; 0 disables)")


def transfer_options(args):
    return TransferOptions(limit_rate=args.limit_rate, retries=args.retries, fragment_retries=args.fragment_retries,
                           sleep_interval=args.sleep_interval)


def add_access_arguments(parser):
    sources = parser.add_mutually_exclusive_group()
    sources.add_argument("--cookies", help="load a Netscape cookie file into memory; source file is not rewritten")
    sources.add_argument("--cookies-from-browser", choices=[
        "brave", "chrome", "chromium", "edge", "firefox", "opera", "safari", "vivaldi", "whale",
    ], help="explicitly read cookies from this browser")
    parser.add_argument("--browser-profile", help="browser profile name/path (requires --cookies-from-browser)")


def access_options(args, parser):
    try:
        return AccessOptions(cookies=args.cookies, browser=args.cookies_from_browser, browser_profile=args.browser_profile)
    except ValueError as error:
        parser.error(str(error))


def positive_height(value):
    height = int(value)
    if height <= 0:
        raise argparse.ArgumentTypeError("quality must be a positive height in pixels")
    return height


def add_media_arguments(parser):
    parser.add_argument("--format-id", help="exact ID or VIDEO_FORMAT_ID+AUDIO_FORMAT_ID from download formats")
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
            format_id=args.format_id,
        )
        if media.audio_only and args.quality is not None:
            raise ValueError("--quality cannot be combined with --audio-only")
        if media.format_id is not None and args.quality is not None:
            raise ValueError("--quality cannot be combined with --format-id")
        return media
    except ValueError as error:
        parser.error(str(error))
