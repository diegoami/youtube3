"""Caption command argument handling and safe error output."""

import argparse
import json
from pathlib import Path

from googleapiclient.errors import HttpError
from . import common


def run(action):
    arguments = common.parser(f'{action.capitalize()} subtitles on your own YouTube video.')
    arguments.add_argument('video_id')
    if action != 'list':
        if action == 'replace':
            arguments.add_argument('caption_id')
        arguments.add_argument('file', type=Path)
        if action == 'upload':
            arguments.add_argument('--language', required=True)
            arguments.add_argument('--name', default='')
        arguments.add_argument('--draft', action=argparse.BooleanOptionalAction, default=None)
        arguments.add_argument('--apply', action='store_true')
    args = arguments.parse_args()
    try:
        youtube = common.client(args)
        if action == 'list':
            result = youtube.list_captions(args.video_id)
        elif action == 'upload':
            result = youtube.upload_caption(args.video_id, args.file, language=args.language, name=args.name,
                                            draft=args.draft if args.draft is not None else False, apply=args.apply)
        else:
            result = youtube.replace_caption(args.video_id, args.caption_id, args.file, draft=args.draft, apply=args.apply)
        print(json.dumps(result, indent=2))
        if action != 'list' and not args.apply:
            print('Dry run: no captions changed. Add --apply.')
    except ValueError as error:
        arguments.exit(1, f'Error: {error}\n')
    except (HttpError, OSError):
        arguments.exit(1, 'Error: caption request failed; inspect tracks before retrying.\n')
