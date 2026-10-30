"""Apply only a manifest's video thumbnails, with preview and checkpointed retries."""

import json
from pathlib import Path

from .common import parser, client
from youtube3 import playlist_artwork, thumbnail_batch


def main():
    arguments = parser(__doc__)
    arguments.add_argument("manifest", type=Path)
    arguments.add_argument("--report", type=Path, help="new checkpoint file; required when applying")
    arguments.add_argument("--retry", type=Path, help="retry an existing report, skipping completed videos")
    arguments.add_argument("--apply", action="store_true")
    args = arguments.parse_args()
    try:
        manifest = playlist_artwork.load_manifest(args.manifest)
        previous = json.loads(args.retry.read_text(encoding="utf-8")) if args.retry else None
        report_path = args.retry or args.report
        if args.apply and report_path is None:
            arguments.error("--report or --retry is required with --apply")
        if args.retry and args.report:
            arguments.error("give --report or --retry, not both")
        if report_path and report_path.resolve() == args.manifest.resolve():
            arguments.error("report must differ from the manifest")
        youtube = client(args)
        if args.apply:
            plan = thumbnail_batch.apply_thumbnail_batch(youtube, manifest, previous=previous, report_path=report_path)
        else:
            plan = thumbnail_batch._retry_plan(thumbnail_batch.plan_thumbnail_batch(youtube, manifest), previous)
        print(json.dumps(plan, indent=2))
        if not args.apply:
            print("Dry run: online validation only; no thumbnails changed. Add --apply.")
    except thumbnail_batch.ThumbnailBatchError as error:
        if error.report:
            print(json.dumps(error.report, indent=2))
        arguments.exit(1, f"Error: {error}\n")
    except (ValueError, OSError) as error:
        arguments.exit(1, f"Error: {error}\n")


if __name__ == "__main__":
    main()
