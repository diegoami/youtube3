"""Preview or upload one local video using a single resumable upload session."""

import json
from pathlib import Path

from .common import client, parser
from youtube3 import upload


def main():
    arguments = parser(__doc__)
    arguments.add_argument("file", type=Path)
    arguments.add_argument("--title", required=True)
    arguments.add_argument("--description", default="")
    arguments.add_argument("--category-id", default="22")
    arguments.add_argument("--tags", help="comma-separated")
    arguments.add_argument("--privacy", choices=("private", "unlisted", "public"), default="private")
    arguments.add_argument("--made-for-kids", action="store_true", default=None)
    arguments.add_argument("--notify-subscribers", action="store_true")
    arguments.add_argument("--retries", type=int, default=3)
    arguments.add_argument("--chunk-size", type=int, default=upload.DEFAULT_CHUNK_SIZE, help="bytes; a multiple of 256 KiB")
    arguments.add_argument("--apply", action="store_true")
    args = arguments.parse_args()
    options = {key: getattr(args, key) for key in ("title", "description", "category_id", "privacy", "made_for_kids",
                                                    "notify_subscribers", "retries", "chunk_size")}
    options["tags"] = args.tags.split(",") if args.tags else None
    try:
        upload.upload_spec(args.file, **options)  # reject invalid input before login
        youtube = client(args)
        plan = upload.plan_video_upload(youtube, args.file, **options)
        print(json.dumps(plan, indent=2))
        if args.apply:
            result = upload.apply_video_upload(youtube, plan, progress=lambda done, total: print(f"Uploaded {done}/{total} bytes"))
            print(json.dumps(result, indent=2))
        else:
            print("Dry run: no upload constructed or sent. Add --apply to upload.")
    except upload.UploadError as error:
        arguments.exit(1, f"Error: {error} (outcome: {error.outcome})\n")
    except (ValueError, OSError) as error:
        arguments.exit(1, f"Error: {error}\n")


if __name__ == "__main__":
    main()
