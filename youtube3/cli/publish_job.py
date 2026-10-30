"""Preview/apply/resume a checkpointed one-video publishing job."""

import json
from pathlib import Path

from .common import client, parser
from youtube3 import publishing_job


def main():
    arguments = parser(__doc__)
    source = arguments.add_mutually_exclusive_group(required=True)
    source.add_argument("--file", type=Path)
    source.add_argument("--video-id")
    source.add_argument("--resume", type=Path)
    arguments.add_argument("--job", type=Path, help="new checkpoint file, required to apply a new job")
    arguments.add_argument("--title")
    arguments.add_argument("--description")
    arguments.add_argument("--tags")
    arguments.add_argument("--thumbnail", type=Path, help="supplied or locally generated artwork")
    arguments.add_argument("--privacy", choices=("private", "unlisted", "public"))
    arguments.add_argument("--schedule")
    arguments.add_argument("--category-id", default="22")
    arguments.add_argument("--made-for-kids", action="store_true", default=None)
    arguments.add_argument("--recover-video-id", help="explicit ID found after an uncertain upload; requires --resume --apply")
    arguments.add_argument("--apply", action="store_true")
    args = arguments.parse_args()
    try:
        if args.resume and (args.job or any(value is not None for value in (args.title, args.description, args.tags,
                                       args.thumbnail, args.privacy, args.schedule, args.made_for_kids))):
            arguments.error("resume uses saved settings; omit new job/settings")
        if args.apply and not (args.job or args.resume):
            arguments.error("--job is required to apply a new publishing job")
        if args.recover_video_id and not (args.resume and args.apply):
            arguments.error("recovery requires --resume and --apply")
        youtube = client(args)
        if args.resume:
            job = publishing_job.load_job(args.resume)
        else:
            job = publishing_job.plan_publishing_job(youtube, file=args.file, video_id=args.video_id,
                title=args.title, description=args.description, tags=args.tags.split(",") if args.tags is not None else None,
                thumbnail=args.thumbnail, privacy=args.privacy, publish_at=args.schedule,
                category_id=args.category_id, made_for_kids=args.made_for_kids)
        print(json.dumps(job, indent=2))
        if args.apply:
            result = publishing_job.apply_publishing_job(youtube, job, args.resume or args.job,
                        resume=args.resume is not None, recover_video_id=args.recover_video_id)
            print(json.dumps(result, indent=2))
        else:
            print("Dry run: no upload, account changes or checkpoint writes. Add --apply.")
    except publishing_job.PublishingJobError as error:
        print(json.dumps(error.job, indent=2))
        arguments.exit(1, f"Error: {error}\n")
    except (ValueError, OSError) as error:
        arguments.exit(1, f"Error: {error}\n")


if __name__ == "__main__":
    main()
