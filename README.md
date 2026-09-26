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

## SEVERAL CHANNELS

A login belongs to the one channel (or brand account) you pick on Google's
consent screen, and the API cannot list the channels you manage. So each
channel is logged in once and saved as a **profile**:

```
python samples/profiles.py adopt caramellalynx   # today's samples/token.json, without logging in again
python samples/profiles.py add diego             # the browser asks which account or brand
python samples/profiles.py list
```

Then give `--profile NAME` to any sample. It prints **"Signed in as <channel>
(<id>)"** before doing anything, checks that the saved login still belongs to
that channel (1 quota unit) and refuses to run otherwise, and names its files
after the profile: `liked-diego.json`, `liked-diego.html`.

-   A profile's channel is recorded when its login is made (`add`, `adopt`)
    and never changed afterwards: a profile whose record is missing or
    unreadable is refused, not rebound to whatever login it has.
-   `profiles.py add NAME` on an existing profile logs in again. The new
    login is kept only if it is for the profile's channel; otherwise the
    old one is put back. The same holds when a saved login has expired and
    the browser opens by itself, and an `add` that was interrupted is
    settled on the profile's next use. While one run logs a profile in
    again, another run on that profile stops with a message instead of
    interfering.

-   Logins are kept in `~/.config/youtube3/profiles/` (on Windows
    `%APPDATA%\youtube3\profiles\`), outside any repository, readable by you
    only.
-   All channels share one quota: 10,000 units a day for the Cloud project.

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

## LANDING PAGE

`youtube3.page` turns an export into one web page of your likes:

```
python samples/build_liked_page.py --from liked.json --out liked.html
```

Open the file in any browser; it needs no server. It shows every like as a
card (thumbnail, title, channel, when you liked it and when it was
published), with a search over titles and channels that ignores case and
accents, a channel filter with counts, five sorts, and a switch to show
deleted and private videos. Everything is inside the one file except the
thumbnails, which load from YouTube's image host (`i.ytimg.com`) and nowhere
else. It is personal data too:
`liked*.html` is ignored by git.

In Python: `youtube3.page.build_page(export, path, title="Liked videos")`,
where `export` is a dict or the path of an export file.

## PUBLISHING

Upload the video in YouTube Studio (videos uploaded through an unaudited API
project are locked private), then set everything else in one command:

```
python samples/publish_video.py VIDEO_ID --title "My title" --thumbnail thumb.jpg --schedule 2026-10-01T18:00
python samples/publish_video.py VIDEO_ID --title "My title" --thumbnail thumb.jpg --schedule 2026-10-01T18:00 --apply
```

-   Without `--apply` it only reads the video and shows each change
    (old -> new), the thumbnail check and the quota cost.
-   `--title`, `--description` or `--description-file`, `--tags a,b`,
    `--private`/`--unlisted`/`--public`, and `--schedule WHEN` (ISO 8601;
    local time without an offset). A scheduled video stays private until
    then; an already public video cannot be scheduled.
-   The thumbnail must be a PNG or JPEG of at most 2 MB and at least 640 px
    wide; 1280x720 is recommended. Custom thumbnails need a phone-verified
    channel (https://www.youtube.com/verify): the plan checks this first
    and refuses the thumbnail, sending nothing, until YouTube says so.
-   YouTube resets every setting of a part it is sent without, so the
    changes are sent together with the video's current settings: nothing
    else (embeddable, license, made for kids, tags, category) changes.
-   Quota: reading 1 unit, updating 50, setting the thumbnail 50.

The same in Python: `youtube3.publish.plan_publish(client, video_id, ...)`
returns the plan, and `youtube3.publish.apply_publish(client, plan)` sends
it.

## WATCH HISTORY

Not supported. YouTube removed the watch history from the Data API in 2016,
and the only other source is a Google export (Takeout or the Data
Portability API), which takes hours and exports whichever account the
browser has selected, not reliably the channel you meant. See it and delete
from it on https://myactivity.google.com.

## YOUTUBECLIENT

The methods of `YoutubeClient`:

-   `login`: Log in with the client secrets and a saved token, and return the API service.
-   `list_channels`: Retrieve information about YouTube channels using their IDs.
-   `like_video`: Like a video by providing its ID.
-   `update_snippet`: Update the snippet information of a video using its ID and the new snippet.
-   `update_status`: Set a video's privacy to private, unlisted or public, keeping its other status settings.
-   `get_channel_snippet`: Retrieve the snippet information of a channel using its ID.
-   `get_channel`: Retrieve information about a channel using its ID.
-   `get_channel_name`: Retrieve the title of a channel using its ID.
-   `get_video`: Retrieve information about a video using its ID.
-   `get_video_content_details`: Retrieve the content details of a video using its ID.
-   `upload_thumbnail`: Set a video's custom thumbnail from a local PNG or JPEG file (max 2 MB; the channel must be verified); `youtube3.publish.check_thumbnail(path)` checks one first.
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
