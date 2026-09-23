# DESCRIPTION

A wrapper around youtube Apis:

- https://developers.google.com/resources/api-libraries/documentation/youtube/v3/python/latest/
- https://developers.google.com/youtube/v3/docs/


## GOAL

I created this package to simplify some typical tasks related to the Youtube API.
See the `samples` directory for examples.

## INSTALL

```
pip install youtube3
```

## USAGE

Create an OAuth client of type "Desktop app" in the Google Cloud console,
enable the YouTube Data API v3, and download its client secrets file. Then:

```
from youtube3 import YoutubeClient
youtube = YoutubeClient("path/to/client_secrets.json")
```

The first run opens the browser to log in (on WSL or a headless machine, open
the printed URL yourself). The login is saved as `token.json` next to the
client secrets, readable by you only (mode `0600` on Linux and macOS; on
Windows an ACL that grants your account alone, not the folder's inherited
permissions), and refreshed on later runs; pass
`token_file=` to keep it elsewhere. Never commit either file.

The library logs what it changes through the `youtube3` logger; call
`logging.basicConfig(level=logging.INFO)` to see it.

The `samples` directory has one script per operation, for example:

```
python samples/show_files_in_playlist.py --playlistId <id>
python samples/move_videos_playlist.py --playlistSource <id> --playlistTarget <id> --start 0 --end 10 --apply
```

Each takes `--client-secrets` (default `samples/client_secrets.json`) and
`--token-file`. The samples that change many things at once (moving,
removing, publishing, unliking) only show what they would do unless given
`--apply`.

## LIKES

`youtube3.likes` exports your liked videos and unlikes them in bulk, safely:

```
python samples/export_liked_videos.py --out liked.json
python samples/unlike_videos.py --from liked.json --channel "Some Channel" --liked-before 2020-01-01
python samples/unlike_videos.py --from liked.json --unavailable --apply   # clears deleted and private ones
python samples/relike_videos.py --from unliked-20260924-120000.json --apply
```

-   The export lists every like, newest first: video id, title, channel, when
    you liked it, when it was published, a thumbnail, and whether it is still
    available (deleted and private videos stay in your likes). Each export
    reports what changed since the previous one.
-   `unlike_videos.py` selects from an export by channel (id or title),
    date, ids or availability; the criteria combine. It shows what it would
    do and changes nothing without `--apply`.
-   YouTube refuses to rate deleted or private videos, so those are removed
    from the Liked videos playlist instead. They cannot be liked again.
-   An applied run writes `unliked-<time>.json`; `relike_videos.py` replays
    it to like the available ones again.
-   Right after a run, the API can still list a removed like for a moment;
    the export is updated by the run itself.
-   Quota: listing costs 1 unit per 50 likes; unliking costs **50 units per
    video** (rating, or removing an unavailable one), out of 10,000 a day. A run rates at most `--limit` (150) videos
    and stops cleanly at the quota; run it again the next day for the rest.

These files are personal data; `.gitignore` keeps them out of git.

## YOUTUBECLIENT

The methods of `YoutubeClient`:

-   `login`: Log in with the client secrets and a saved token, and return the API service.
-   `list_channels`: Retrieve information about YouTube channels using their IDs.
-   `like_video`: Like a video by providing its ID.
-   `update_snippet`: Update the snippet information of a video using its ID and the new snippet.
-   `update_status`: Set a video's privacy to private, unlisted or public.
-   `get_channel_snippet`: Retrieve the snippet information of a channel using its ID.
-   `get_channel`: Retrieve information about a channel using its ID.
-   `get_channel_name`: Retrieve the title of a channel using its ID.
-   `get_video`: Retrieve information about a video using its ID.
-   `get_video_content_details`: Retrieve the content details of a video using its ID.
-   `upload_thumbnail`: Set a video's custom thumbnail from a local image file (max 2 MB; the channel must be verified).
-   `get_video_snippet`: Retrieve the snippet information of a video using its ID.
-   `get_channel_id`: Retrieve the ID of a channel that a video belongs to using the video's ID.
-   `get_subscriptions_channel_ids`: Retrieve one page of the IDs and titles of the channels you are subscribed to.
-   `get_channels`: Retrieve your own channel's content details.
-   `iterate_subscriptions_in_channel`: Iterate over all the channels you are subscribed to.
-   `liked_channel`: Retrieve the ID of the playlist of your liked videos.
-   `iterate_liked_videos`: Iterate over your liked videos as records (see LIKES), newest like first.
-   `playlist_snippet`: Retrieve the snippet information of a playlist using its ID.
-   `playlist_name`: Retrieve the title of a playlist using its ID.
-   `videos_in_playlist`: Retrieve one page (up to 50) of the videos in a playlist.
-   `iterate_videos_in_playlist`: Iterate over a playlist page by page, at most `maxCount` pages when given.
-   `delete_from_playlist`: Remove the videos at positions `start` to `end - 1` from a playlist; `apply=False` only lists them. Returns the video ids.
-   `copy_to_playlist`: Copy the videos at positions `start` to `end - 1` of a playlist to another; `apply=False` only lists them. Returns the video ids.
-   `subscribe_channel`: Subscribe to a channel using its ID.
-   `verify_video`: Say whether a video exists and can be watched in a country (default `DE`): not in its blocked list, and in its allowed list when it has one.

### Upgrading from 1.x

Version 2.0.0 breaks the 1.x API:

-   `get_related_videos`, `iterate_related_videos` and `get_recommended` are
    removed: YouTube no longer serves related videos or recommendations
    through the API.
-   `login` returns the API service alone, not a `(service, flags)` tuple:
    replace `service, flags = youtube.login(path)` with
    `service = youtube.login(path)`.
-   `YoutubeClient(client_json_file=None, debug=False, *, token_file=None,
    service=None)`: the client secrets file is read from the path given
    (1.x read `client_secrets.json` from that path's directory, whatever the
    file name); the login is saved in `token.json` next to it, not in
    `youtube.dat`, so the first 2.0 run logs in again; `service=` passes an
    already-built client instead of logging in.
-   `oauth2client` is no longer a dependency.
-   `ChannelNotFoundException` is an `Exception`, no longer a
    `BaseException`.
-   `verify_video` returns `False` only for an API error (`HttpError`);
    other exceptions now propagate instead of being printed and swallowed.
-   What the library changes is logged through the `youtube3` logger instead
    of printed.
-   `copy_to_playlist` and `delete_from_playlist` act on positions `start`
    to `end - 1` for any `start`; in 1.x a `start` above 0 did nothing.

## DEVELOPMENT

Python 3.11 or newer. BSD-3-Clause licensed (`LICENSE`).

```
pip install -e ".[dev]"
ruff check
pytest
```

The tests run offline: they build the client over canned responses
(`tests/conftest.py`) and never touch a real account. The process for changes
is in `CLAUDE.md`, the requests in `ROADMAP.md`.
