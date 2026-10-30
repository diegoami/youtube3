"""Preview and save a fixed publishing batch; account writes are never part of planning."""

import json
from pathlib import Path

from .common import client, parser
from youtube3 import publishing_batch


def main():
    arguments = parser(__doc__)
    arguments.add_argument("action", choices=("plan",))
    arguments.add_argument("configuration", type=Path)
    arguments.add_argument("--out", type=Path, help="explicitly save the plan without uploading")
    args = arguments.parse_args()
    try:
        overrides = {"profile": args.profile} if args.profile is not None else {}
        entries = publishing_batch.resolve_batch(args.configuration, overrides=overrides)
        args.profile = entries[0]["settings"].get("profile", args.profile)
        plan = publishing_batch.plan_batch(client(args), entries)
        print(json.dumps(plan, indent=2))
        if args.out:
            publishing_batch.save_plan(plan, args.out)
            print(f"Plan saved to {args.out}")
        print("Preview: no uploads or account writes.")
    except (ValueError, OSError, TypeError) as error:
        arguments.exit(1, f"Error: {error}\n")


if __name__ == "__main__":
    main()
