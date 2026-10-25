"""Arguments shared by download commands, without OAuth setup."""

import argparse

from youtube3.download import MediaOptions


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
