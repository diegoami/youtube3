from pathlib import Path

from _common import client, parser

from youtube3 import publish

if __name__ == "__main__":
    arguments = parser("Set a video's thumbnail and metadata, and make it public now or later; a dry run unless --apply.")
    arguments.add_argument("video_id")
    arguments.add_argument("--title")
    text = arguments.add_mutually_exclusive_group()
    text.add_argument("--description")
    text.add_argument("--description-file", type=Path)
    arguments.add_argument("--tags", help="comma-separated")
    arguments.add_argument("--thumbnail", type=Path, help="a PNG or JPEG, at most 2 MB, ideally 1280x720")
    privacy = arguments.add_mutually_exclusive_group()
    for level in publish.PRIVACY:
        privacy.add_argument(f"--{level}", dest="privacy", action="store_const", const=level)
    arguments.add_argument("--schedule", help="when it goes public, ISO 8601; local time without an offset")
    arguments.add_argument("--apply", action="store_true", help="really change the video")
    args = arguments.parse_args()

    description = args.description_file.read_text(encoding="utf-8") if args.description_file else args.description
    youtube = client(args)
    plan = publish.plan_publish(
        youtube,
        args.video_id,
        title=args.title,
        description=description,
        tags=args.tags.split(",") if args.tags is not None else None,
        thumbnail=args.thumbnail,
        privacy=args.privacy,
        publish_at=args.schedule,
    )
    print(f"{plan['video_id']}: {plan['title']}")
    for field, (old, new) in plan["changes"].items():
        if field == "description":
            print(f"  description: {len(old or '')} -> {len(new or '')} characters")
        else:
            print(f"  {field}: {old!r} -> {new!r}")
    if plan["thumbnail"]:
        report = plan["thumbnail"]
        size = f", {report['width']}x{report['height']}" if report["width"] else ""
        print(f"  thumbnail: {report['path']} ({report['type'] or 'unknown type'}{size})")
        for warning in report["warnings"]:
            print(f"    warning: {warning}")
    if not plan["changes"] and not plan["thumbnail"]:
        print("  nothing to change")
    for error in plan["errors"]:
        print(f"Error: {error}")
    if plan["errors"]:
        raise SystemExit(1)
    print(f"Quota: {plan['cost']} units.")
    if not args.apply:
        print("Dry run: nothing changed. Add --apply to do it.")
    else:
        done = publish.apply_publish(youtube, plan)
        print(f"Done: {', '.join(done) or 'nothing'}.")
