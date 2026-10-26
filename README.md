# DESCRIPTION

A wrapper around youtube Apis:

- https://developers.google.com/resources/api-libraries/documentation/youtube/v3/python/latest/
- https://developers.google.com/youtube/v3/docs/


## GOAL

I created this package to simplify some typical tasks related to the Youtube API.
The installed `youtube3` command provides the common operations; the Python
API remains available for applications that need more control.

## INSTALL

```
pip install youtube3
```

This installs the library and the `youtube3` command:

```
youtube3 --help
```

## OPTIONAL DOWNLOADS (POC)

Install the optional downloader from this checkout in a virtual environment
(the environment can live anywhere):

```bash
python3 -m venv ~/.venvs/youtube3
source ~/.venvs/youtube3/bin/activate
python -m pip install -e ".[download]"
youtube3 download video VIDEO_ID --dry-run
youtube3 download video VIDEO_ID --output ./videos --quality 720
```

Download one public video using a video ID, an HTTPS
YouTube watch URL or a youtu.be link. It uses no Google login, saved profiles or
browser cookies. A watch link containing a playlist still selects only that video.
`--quality` limits the height; the actual resolution depends on available formats.
Existing files are preserved and interrupted downloads can resume.
After this feature is released, install it with `pip install "youtube3[download]"`.

Preview a public playlist, or a range using **1-based, inclusive** positions:

```bash
youtube3 download playlist PLAYLIST_ID --output ./videos
youtube3 download playlist PLAYLIST_ID --output ./videos --start 2 --end 10
youtube3 download playlist PLAYLIST_ID --output ./videos --start 2 --end 10 --apply
```

Without `--apply`, the playlist command only reads public playlist metadata
and prints the selection; `--dry-run` explicitly requests the same preview.
This requires the download extra and read-only network access, and writes no
files. Each entry shows whether it will download or skip as archived,
unavailable or duplicated. The preview does not verify media availability.
With `--apply`, it prints the selection and downloads those exact video IDs,
without rereading the playlist. Numbered filenames preserve the original
playlist positions, such as `00002 - Title [video-id].mp4`.

Both commands use `OUTPUT/.youtube3-download-archive.txt` to remember completed
YouTube video IDs. Repeating a download to the same output folder skips those
IDs even if their titles change. yt-dlp records completion after downloading
and postprocessing; a failure stops the run, and rerunning retries the
unfinished entries. Use `--archive PATH` on either command to share a different
archive across output folders. Its parent folder is created only when downloading.
The archive is the record of completion: if you delete a media file and want
to fetch it again, remove its `youtube VIDEO_ID` line from the archive first.

For longer playlists, optionally continue after individual failures and save
per-video results:

```bash
youtube3 download playlist PLAYLIST_ID --output ./videos --apply --continue-on-error --report run-1.json
youtube3 download retry run-1.json
youtube3 download retry run-1.json --apply --continue-on-error --report run-2.json
```

`--continue-on-error` and `--report` are independently optional. The default
still stops at the first failure. A run with any failed downloads exits with
status 1 even when it continues through the remaining entries. Reports require
`--apply` and a **new** file path; existing files are preserved. A report is
created before the first download and checkpointed after each result. It records
`downloaded`, `failed`, `skipped` and `not_attempted` entries, plus the selected
IDs, original positions, quality, media options and absolute output/archive paths.
It excludes raw backend errors and media URLs; download errors appear in the
terminal. Keep reports locally if playlist titles or local paths are personal.

`download retry` previews **only failed entries** offline, without the download
extra. `--apply` uses the saved settings and original positions without rereading
the playlist, and rechecks the archive so already completed IDs are skipped.
Reports refer to paths on the machine that created them. A retry report can
itself be used for another retry; use a fresh `--report` path each time.
Entries marked `not_attempted` after an interruption or an early stop are not
retried by this command: rerun the original playlist selection to finish them.
The archive remains the completion record if a run is interrupted between a
download and its report checkpoint.

Limit media transfer bandwidth and automatic retry attempts when needed:

```bash
youtube3 download video VIDEO_ID --limit-rate 1.5M --retries 3 --fragment-retries 2
youtube3 download playlist PLAYLIST_ID --apply --limit-rate 500K --retries 0 --report limited-run.json
```

`--limit-rate` is in **bytes per second**. K, M and G use powers of 1024;
`500K`, `2MiB` and raw byte counts are accepted. The cap applies per media
transfer. `--retries` limits HTTP retries after the initial attempt, and
`--fragment-retries` limits retries per media fragment. Both take nonnegative
integers; zero disables the corresponding retries. Omitted settings retain
yt-dlp defaults. These controls are passed to the
[yt-dlp media downloader](https://github.com/yt-dlp/yt-dlp#download-options);
they do not change playlist metadata requests or the batch stop/continue policy.
Previews display the settings without transferring media.

Batch reports save these controls and `download retry` reuses them. New reports
use schema version 3; existing version-1 reports still work using default
transfer settings, and version-2 reports retain their saved limits.
Older youtube3 checkouts reject newer report versions rather
than silently discarding the saved limits.

Inspect formats before downloading. This lists format IDs, containers,
resolutions, codecs and known sizes (`~` marks an estimate); it reads metadata
online without downloading media or writing files:

```bash
youtube3 download formats VIDEO_ID
```

Use a format ID from that list to select a particular stream, or combine a
video-only ID and an audio-only ID:

```bash
youtube3 download video VIDEO_ID --format-id 18
youtube3 download video VIDEO_ID --format-id 137+140
youtube3 download video VIDEO_ID --audio-only --format-id 140 --audio-format mp3
youtube3 download playlist PLAYLIST_ID --format-id 18 --apply --report formats-run.json
```

These IDs are examples; use the IDs available for your video. A single ID
downloads exactly that stream, which may contain video, audio or both. A
`VIDEO_ID+AUDIO_ID` pair requires video-only followed by audio-only and checks
for FFmpeg and ffprobe before downloading. `--audio-only` accepts a single
audio-only ID and still supports conversion. Exact selection cannot be combined
with `--quality`, and it does not fall back to a different format if unavailable.
The option accepts IDs, not arbitrary yt-dlp format expressions.

Exact selections add `[format-IDS]` to filenames and `-format-IDS` to their
default archive names, for example `.youtube3-download-archive-format-137+140.txt`.
This lets different choices coexist in the same output folder. An explicit
custom `--archive` still deduplicates only by video ID; use different custom
archive paths to keep multiple selections. Playlist numbering is preserved,
and reports save the exact choice for `download retry`. Previewing a playlist
does not check whether every entry offers that format; unavailable choices
fail on apply and can be recorded with the existing batch reporting options.

For audio only, keep the native audio container or explicitly convert it:

```bash
youtube3 download video VIDEO_ID --audio-only --output ./audio
youtube3 download video VIDEO_ID --audio-only --audio-format mp3 --output ./audio
youtube3 download playlist PLAYLIST_ID --audio-only --output ./audio
youtube3 download playlist PLAYLIST_ID --audio-only --output ./audio --apply
```

Native audio selects an audio-only stream. `--audio-format` supports `mp3`,
`m4a`, `opus`, `flac` and `wav`, requires `--audio-only`, and checks for the
FFmpeg and ffprobe executables before downloading. `--quality` applies to
video and cannot be combined with `--audio-only`. A single-video audio dry
run works without these tools or the optional downloader.

Audio uses separate default archives: `.youtube3-download-archive-audio-native.txt`
or `.youtube3-download-archive-audio-FORMAT.txt` in the output folder. Downloading
a video therefore does not suppress a later audio download. Audio filenames
also include `[audio-native]` or `[audio-FORMAT]`, in addition to any exact
`[format-IDS]` marker. Each mode has its own media and postprocessing input,
so conversion preserves previously downloaded video or native audio files.
Playlist position prefixes remain in place. An explicit
`--archive PATH` continues to deduplicate by video ID regardless of media mode;
use different custom archive paths when you want both modes.

Save captions, metadata and thumbnails alongside media with opt-in flags,
supported by both video and playlist commands:

```bash
youtube3 download video VIDEO_ID --subtitles en,de --write-metadata --write-thumbnail
youtube3 download playlist PLAYLIST_ID --subtitles en --auto-subtitles --write-metadata --apply
```

`--subtitles` takes comma-separated language codes, such as `en,de,pt-BR`.
`--auto-subtitles` also permits automatic captions for those languages; manual
captions take priority when both exist. Available captions are saved separately
in VTT format when offered, otherwise the best available subtitle format.
Missing caption languages or thumbnails are reported by yt-dlp and do not
prevent the media download. Metadata is saved as `.info.json`; thumbnails use
their supplied image format. These flags do not add sidecars to an ID already
in the archive: use a new `--archive PATH` to revisit it. Existing files are
preserved.

The base `pip install youtube3` does not install yt-dlp. Download help and
the single-video `--dry-run` also work without the extra. That dry run prints
the plan without contacting YouTube, checking availability or creating files.

Install the **FFmpeg executable** separately to merge video and audio streams.
For full YouTube support, yt-dlp also needs a supported JavaScript runtime
(Deno is recommended upstream); the extra includes its EJS Python component.
See [yt-dlp's dependency instructions](https://github.com/yt-dlp/yt-dlp#dependencies).
The extra does not install these external executables. YouTube extraction may
need yt-dlp updates as the site changes; upgrade with
`pip install --upgrade "yt-dlp[default]"`.

Authenticated downloads are outside this feature.
Media retrieval from YouTube has not been live-verified; automated tests use
canned metadata and local media transport, including checks with real yt-dlp
and conversion of generated audio with FFmpeg when available.

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

Set up OAuth client secrets once, then create a profile for the channel or
brand account you want to use:

```
youtube3 setup path/to/client_secrets.json
youtube3 profiles add caramellalynx
youtube3 profiles list
```

Use `youtube3 <command> --help` for all options. Examples:

```
youtube3 playlist show --playlistId <id>
youtube3 playlist move --playlistSource <id> --playlistTarget <id> --start 0 --end 10 --apply
youtube3 likes export --out liked.json
youtube3 video check --videoId <id> --country DE
```

Operations that change many things (moving, removing, publishing and
unliking) are dry runs unless given `--apply`. The equivalent Python API is
documented below and is unchanged.

## SEVERAL CHANNELS

A login belongs to the one channel (or brand account) you pick on Google's
consent screen, and the API cannot list the channels you manage. So each
channel is logged in once and saved as a **profile**:

```
youtube3 profiles adopt caramellalynx   # an existing token, without logging in again
youtube3 profiles add diego             # the browser asks which account or brand
youtube3 profiles list
```

Then give `--profile NAME` to any command. It prints **"Signed in as <channel>
(<id>)"** before doing anything, checks that the saved login still belongs to
that channel (1 quota unit) and refuses to run otherwise, and names its files
after the profile: `liked-diego.json`, `liked-diego.html`.

-   Each profile is one file, `~/.config/youtube3/profiles/NAME.json` (on
    Windows `%APPDATA%\youtube3\profiles\NAME.json`), outside any
    repository and readable by you only. It holds the channel and its login
    together, and is only ever replaced whole, by a login whose channel
    checked out. A login that fails, is interrupted or runs at the same time
    as another leaves the old profile or the new one, never a mix.
-   A profile's channel is recorded when its login is made (`add`, `adopt`)
    and never changed afterwards: a profile with no channel, or an
    unreadable file, is refused, not rebound to whatever login it has.
-   `youtube3 profiles add NAME` on an existing profile logs in again, and keeps
    the new login only if it is for the profile's channel. The same holds
    when a saved login has expired and the browser opens by itself. `add`
    also repairs a profile that is refused as unreadable or without a
    channel.
-   All channels share one quota: 10,000 units a day for the Cloud project.

## LIKES

`youtube3.likes` exports your liked videos and unlikes them in bulk, safely:

```
youtube3 likes export --out liked.json
youtube3 likes unlike --from liked.json --channel "Some Channel" --liked-before 2020-01-01
youtube3 likes unlike --from liked.json --unavailable --apply   # clears deleted and private ones
youtube3 likes relike --from unliked-20260924-120000.json --apply
```

-   The export lists every like, newest first: video id, title, channel, when
    you liked it, when it was published, a thumbnail, and whether it is still
    available (deleted and private videos stay in your likes). Each export
    reports what changed since the previous one.
-   `youtube3 likes unlike` selects from an export by channel (id or title),
    date, ids or availability; the criteria combine. It shows what it would
    do and changes nothing without `--apply`.
-   YouTube refuses to rate deleted or private videos, so those are removed
    from the Liked videos playlist instead. They cannot be liked again.
-   An applied run writes `unliked-<time>.json`; `youtube3 likes relike` replays
    it to like the available ones again.
-   Right after a run, the API can still list a removed like for a moment;
    the export is updated by the run itself.
-   Quota: listing costs 1 unit per 50 likes; unliking costs **50 units per
    video** (rating, or removing an unavailable one), out of 10,000 a day. A run rates at most `--limit` (150) videos
    and stops cleanly at the quota; run it again the next day for the rest.

These files are personal data; `.gitignore` keeps them out of git.

## YOUR CHANNEL

`youtube3.channel` lists every video uploaded to the channel you are signed in
as (the profile's channel), private and unlisted included:

```
youtube3 channel videos --out channel.json
```

-   It prints one line per video, newest upload first: id, published date,
    privacy, views, duration and title, and writes the same to a JSON export
    (default `channel.json`, or `channel-<profile>.json`).
-   Quota: 1 unit per 50 videos for the listing, plus 1 unit per 50 for the
    privacy, views and duration.

In Python: `youtube3.channel.export_channel_videos(client, path)`, or
`client.iterate_channel_videos()` for the records themselves.

## LANDING PAGE

`youtube3.page` turns an export into one web page of your likes:

```
youtube3 likes page --from liked.json --out liked.html
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
youtube3 publish VIDEO_ID --title "My title" --thumbnail thumb.jpg --schedule 2026-10-01T18:00
youtube3 publish VIDEO_ID --title "My title" --thumbnail thumb.jpg --schedule 2026-10-01T18:00 --apply
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
-   `uploads_playlist`: Retrieve the id of your own channel's uploads playlist.
-   `iterate_channel_videos`: Iterate over the videos uploaded to your channel as records (see YOUR CHANNEL), newest first.
-   `iterate_subscriptions_in_channel`: Iterate over all the channels you are subscribed to.
-   `liked_channel`: Retrieve the ID of the playlist of your liked videos.
-   `iterate_liked_videos`: Iterate over your liked videos as records (see LIKES), newest like first.
-   `playlist_snippet`: Retrieve the snippet information of a playlist using its ID.
-   `playlist_name`: Retrieve the title of a playlist using its ID.
-   `videos_in_playlist`: Retrieve one page (up to 50) of the videos in a playlist.
-   `video_details`: Retrieve one page (up to 50) of videos' snippet, content details, statistics and status, keyed by id.
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
is in `AGENTS.md`, the requests in `ROADMAP.md`.
