"""Shared by unlike_videos.py and relike_videos.py: show the plan, then apply it."""

from youtube3 import likes


def show(videos, verb):
    for video in videos:
        liked = (video.get("liked_at") or "")[:10]
        channel = video.get("channel_title") or "-"
        print(f"  {liked}  {video['video_id']}  {channel}  {video.get('title')}")
    print(f"{len(videos)} videos to {verb}.")


def run(youtube, videos, rating, apply, limit, log_folder):
    """Unlike or like again, write the undo log, and return the records done."""
    verb = "unlike" if rating == "none" else "like again"
    act = likes.unlike_videos if rating == "none" else likes.like_videos
    result = act(youtube, videos, apply=apply, limit=limit)
    planned = [v for v in videos if v["video_id"] in set(result["planned"])]
    show(planned, verb)
    print(f"Quota: {result['cost']} of {likes.DAILY_QUOTA} units a day.")
    if result["over_limit"]:
        print(f"{len(result['over_limit'])} more are over --limit {limit}; run again tomorrow for them.")
    if not apply:
        print("Dry run: nothing changed. Add --apply to do it.")
        return []
    done = [v for v in planned if v["video_id"] in set(result["done"])]
    if done:
        print(f"Done: {len(done)}. Undo log: {likes.write_undo_log(log_folder, done, rating)}")
    for video_id, reason in result["failed"].items():
        print(f"Failed: {video_id} ({reason})")
    if result["stopped"]:
        print(f"Stopped ({result['stopped']}): {len(result['not_done'])} not done; run again later.")
    return done
