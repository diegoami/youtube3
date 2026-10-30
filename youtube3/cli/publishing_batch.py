"""Plan, preview, run, pause and recover fixed publishing batches."""

import json
from pathlib import Path

from .common import client, parser
from youtube3 import publishing_batch, publishing_queue


def main():
    arguments = parser(__doc__)
    arguments.add_argument("action", choices=("plan", "run", "resume", "retry", "status", "pause", "recover"))
    arguments.add_argument("source", type=Path, help="configuration for plan, saved plan for run, queue checkpoint otherwise")
    arguments.add_argument("--out", type=Path)
    arguments.add_argument("--queue", type=Path, help="new queue checkpoint for run")
    arguments.add_argument("--ledger", type=Path, help="shared per-channel upload ledger (default: config publishing folder)")
    arguments.add_argument("--entry", action="append", help="select stable entry IDs")
    arguments.add_argument("--stage", choices=(*publishing_queue.jobs.STAGES, "playlist"))
    arguments.add_argument("--limit", type=int)
    arguments.add_argument("--continue-on-error", action="store_true")
    arguments.add_argument("--video-id", help="explicit recovered ID, after inspecting an uncertain upload")
    arguments.add_argument("--missing-playlist", help="confirm this uncertain membership is missing before retrying")
    arguments.add_argument("--confirm-not-uploaded", action="store_true", help="explicitly confirm no upload exists before allowing a new attempt")
    arguments.add_argument("--apply", action="store_true")
    args = arguments.parse_args()
    try:
        if args.action == "plan":
            entries = publishing_batch.resolve_batch(args.source, overrides={"profile": args.profile} if args.profile else {})
            args.profile = entries[0]["settings"].get("profile", args.profile)
            plan = publishing_batch.plan_batch(client(args), entries)
            print(json.dumps(plan, indent=2))
            if args.out:
                publishing_batch.save_plan(plan, args.out)
            print("Preview: no uploads or account writes.")
            return
        if args.action == "status":
            print(json.dumps(publishing_queue.status(args.source), indent=2))
            return
        if args.action == "pause":
            publishing_queue.request_pause(args.source)
            print("Pause requested; the runner stops before the next stage/account write.")
            return
        if args.action == "run":
            if args.queue is None:
                arguments.error("run requires a new --queue path")
            plan = publishing_batch.load_plan(args.source)
        else:
            queue = publishing_queue.load_queue(args.source)
            plan = queue["plan"]
            if args.queue or args.ledger:
                arguments.error("existing queues use their saved checkpoint and ledger paths")
        if not args.apply:
            print(json.dumps(plan, indent=2))
            print("Dry run: no queue/ledger writes, uploads or account changes. Add --apply.")
            return
        if args.profile is None:
            args.profile = plan["profile"]
        youtube = client(args)
        if args.action == "recover":
            if not args.entry or len(args.entry) != 1:
                arguments.error("recover requires one --entry")
            result = publishing_queue.recover_entry(youtube, args.source, args.entry[0], video_id=args.video_id, missing_playlist=args.missing_playlist, confirm_not_uploaded=args.confirm_not_uploaded)
        else:
            if args.action == "run":
                publishing_queue.initialize_queue(plan, args.queue, ledger_path=args.ledger)
            checkpoint = args.queue if args.action == "run" else args.source
            result = publishing_queue.run_queue(youtube, checkpoint, resume=args.action in ("resume", "retry"),
                retry=args.action == "retry", select=args.entry, stage=args.stage, limit=args.limit,
                continue_on_error=args.continue_on_error)
        print(json.dumps({"state": result["state"], "entries": result["entries"]}, indent=2))
        if result["state"] in ("failed", "blocked"):
            raise SystemExit(1)
    except publishing_queue.QueueError as error:
        if error.queue:
            print(json.dumps({"state": error.queue["state"], "entries": error.queue["entries"]}, indent=2))
        arguments.exit(1, f"Error: {error}\n")
    except (ValueError, OSError, TypeError) as error:
        arguments.exit(1, f"Error: {error}\n")


if __name__ == "__main__":
    main()
