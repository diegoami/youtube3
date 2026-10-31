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
YouTube watch URL or a youtu.be link. It uses no Google API login or saved profiles;
browser cookies are used only when explicitly requested below.
A watch link containing a playlist still selects only that video.
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

Before extraction, youtube3 checks PATH for `deno`, `node` and `qjs` and enables
the discovered runtimes in yt-dlp. yt-dlp checks their versions and chooses a
usable runtime; finding an executable alone does not establish compatibility.
The download extra requires yt-dlp 2025.11.12 or newer, which supports this
runtime configuration; reinstalling the extra upgrades older versions.
Install Deno (recommended), Node 22+ or a supported QuickJS version using
[the upstream runtime setup guide](https://github.com/yt-dlp/yt-dlp/wiki/EJS).
For WSL, install the runtime inside the WSL environment running youtube3.
If none is found, youtube3 warns before extraction and continues: some metadata
or formats may still be available. This check covers format inspection,
playlist previews, video/playlist downloads and applied batch retries.
Single-video dry runs and report retry previews stay offline without probing
runtimes. Runtime selection follows the current PATH each time; no runtime path
or setting is saved in batch reports. Custom runtime paths are not exposed as
wrapper options.

HTTP 429 means YouTube is rate limiting requests; stop requests and try again
later. A sign-in/bot challenge means public extraction is blocked. youtube3
reports these separately from missing runtimes and does not add an automatic
retry for either error. Installing a runtime does not guarantee either block
will clear. Playlist enumeration can succeed even when downloading its videos
is blocked. HTTP 429, yt-dlp's “rate-limited by YouTube” session error, and
bot/CAPTCHA challenges stop the playlist/batch even with
`--continue-on-error`; remaining entries stay `not_attempted`. Retry selects
failed entries only: rerun the original selection to include unattempted entries.

New video/playlist CLI runs default to five seconds between successive video
extraction attempts. Use `--sleep-interval 10` to increase this interval, or
`--sleep-interval 0` to disable it. This spaces extraction attempts, not media
bandwidth or every individual HTTP request. The library leaves pacing unchanged
unless `TransferOptions(sleep_interval=...)` is supplied. Reports preserve the
interval; `download retry --sleep-interval N` overrides it. Older reports retain
their original unpaced behavior unless overridden.

You may explicitly supply cookies to video, formats, playlist and retry commands:

```bash
youtube3 download video VIDEO_ID --cookies /path/to/youtube-cookies.txt
youtube3 download formats VIDEO_ID --cookies-from-browser firefox
youtube3 download playlist PLAYLIST_ID --cookies-from-browser firefox --browser-profile default --apply --report run.json
youtube3 download retry run.json --cookies-from-browser firefox --apply
```

Choose either a Netscape cookie file or a browser. `--browser-profile` accepts
a profile name/path and requires `--cookies-from-browser`. Browser extraction
uses the selected browser's local profiles; on WSL a Windows browser profile
may not be accessible or decryptable from Linux. Use a browser in the environment
running yt-dlp, or explicitly supply a compatible cookie file.
Cookie files are loaded into memory and the supplied file is not rewritten.
Malformed files are rejected without displaying their contents. With cookies
enabled, raw backend diagnostics are suppressed to avoid exposing session data.
Reports save only that cookies were used, not the cookie source, browser/profile
or cookie contents; applying a retry requires explicitly supplying cookies again.
Single-video dry runs and report previews do not read cookies or browser profiles.
Format inspection and playlist previews read metadata online and **do access the
requested cookie source**, even without `--apply`.

Cookies are session credentials: keep exported files outside the repository and
do not share them. Account use can result in temporary or permanent restrictions;
use cookies only when necessary. Cookies do not guarantee access or remove rate
limits. See [yt-dlp's YouTube cookie guidance](https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies).
Google API OAuth profiles remain separate. PO-token providers and automatic
browser challenges are not included.

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

## LOCAL ARTWORK

Install `pip install "youtube3[artwork]"` for Pillow image rendering and PyYAML
configuration support. The base installation and help work without them.
No owner artwork or fonts are distributed.

```sh
youtube3 artwork render --background template.png --out episode99.png --episode 99
youtube3 artwork render --background template.png --out episode99.png --episode 99 --apply
youtube3 artwork render --background template.png --out cover.png --preset cover --text "My series" --apply
```

The default is a preview: it generates no image and makes no account calls.
`--apply` renders locally. The video preset is 1280×720; cover is 1280×1280.
`--size WIDTH HEIGHT` overrides dimensions. `--fit cover` center-crops;
`contain` pads in black; `stretch` distorts to fill the output. Text uses
`--font FILE`, `--font-size`, `--color` and `--position X Y` in output pixels.
An omitted font uses Pillow's built-in scalable font. Text must fit entirely;
invalid inputs/layouts fail with an actionable error. `--text "Episode {episode}"`
substitutes a minimum two-digit episode number, including 100 and 1000.
Inputs are preserved. Existing outputs require explicit `--overwrite`.

Python: `youtube3.artwork.plan_thumbnail(background, output, ...)` returns a
serializable preview; `render_thumbnail(background, output, ...)` or
`render_plan(plan)` writes an image and returns its path. These are local
functions and do not require a `YoutubeClient` or login.

Migration from `lynxupercluster_thumbnailgenerator`: pass its existing YAML
(or equivalent JSON) to `youtube3 artwork render --config config.yaml`, then
add `--apply` to render. `legacy_plans(config_path)` exposes the same plans in
Python. All documented fields are supported: `orig_file`, `output_dir`,
`font.name/size/color.r/g/b`, `coords.x2/x3/y`, `start_range` and `end_range`.
The range remains exclusive at the start and inclusive at the end (defaults
0 and 1000). Filenames remain `thumbnail<N>.png`; two-digit numbers are padded.
Coordinates and font size apply to the source before stretching to 1280×720.
Numbers of four or more digits use `x3` and must fit, rather than disappearing.
Relative paths resolve next to the config file. All destinations are checked
before the first render; a later rendering error can leave earlier outputs.

### Create a playlist

```sh
youtube3 playlist create "My series" --profile mybrand
youtube3 playlist create "My series" --description "Series episodes" --profile mybrand --apply
```

Preview shows the verified destination channel and request body without creating
a playlist. `--apply` creates one empty **private** playlist and prints its ID and
URL, ready to use in a publishing batch's `playlists` list. `--privacy unlisted`
or `--privacy public` explicitly selects another visibility.

Python: `client.create_playlist("My series", description="Series episodes",
privacy="private", apply=False)` returns `{plan, applied, response}`. `plan`
contains the destination `channel` and request `body`; `response` is `None` for
preview, or the created playlist resource (including `id`) when applied.
Invalid title/description/privacy fails before any API call. Preview may read
the destination channel but never inserts a playlist. Each applied call creates
a new playlist; titles are not unique and creation is not idempotent. Inserts
are never automatically retried. After a request error or missing returned ID,
inspect the channel before creating again to avoid duplicates.

Contract checked 2026-10-31 against Google's
[playlists.insert reference](https://developers.google.com/youtube/data/reference/rest/v3/playlists/insert):
`part=snippet,status`, `snippet.title` required, optional `snippet.description`
and `status.privacyStatus`, existing `youtube` OAuth scope, 50 quota units per
insert. Live verification remains a separate owner-approved G5 check.

### Playlist artwork

```sh
youtube3 artwork playlist --playlist-id PLAYLIST_ID --profile mybrand --background base.png --output-dir artwork
youtube3 artwork playlist --snapshot snapshot.json --background base.png --output-dir artwork --save-plan plan.json
youtube3 artwork playlist --plan plan.json --apply
```

`--playlist-id` reads metadata online; `--snapshot` and `--plan` are entirely
offline. No option here writes to YouTube. A default preview writes no files;
`--save-plan FILE` explicitly saves only the mapping. `--apply` saves the
manifest (default `OUTPUT_DIR/artwork.json`) before generating images.

Snapshot format: `{"playlist_id":"PL...","title":"My series","items":[
{"video_id":"VIDEO_ID","position":1,"title":"First","available":true}]}`.
Positions are 1-based originals; `--start`/`--end` are inclusive. Episode numbers
are original position plus `--number-offset`; gaps/unavailable entries keep
their numbers. Unavailable entries (`available:false`) get no image. Duplicate
videos get separate position-prefixed filenames; later application must reject
ambiguous duplicate-ID mappings. Each manifest includes a distinct square
`cover` entry. The default video text is `Episode {episode}`; `--text`,
`--cover-text`, font/color/position options customize it. Existing outputs
require `--overwrite`. Rendering from a saved plan never refetches the playlist.
A later rendering failure may leave earlier files; the saved mapping remains
available for inspection/regeneration.

Python: `youtube3.playlist_artwork.playlist_snapshot(client, playlist_id)` reads
metadata; `plan_playlist_artwork(snapshot, background, output_dir, ...)` fixes
the mapping; `save_manifest`/`load_manifest` persist it;
`render_playlist_artwork(manifest, overwrite=False)` renders offline.

### Apply video artwork

```sh
youtube3 artwork apply artwork/artwork.json --profile mybrand
youtube3 artwork apply artwork/artwork.json --profile mybrand --report results.json --apply
youtube3 artwork apply artwork/artwork.json --profile mybrand --retry results.json --apply
```

The preview reads channel/video metadata but writes nothing. Applying requires
an explicit new report path or an existing retry report. Every image is decoded
and fingerprinted, every video must belong to the selected channel, and custom
thumbnail eligibility must be enabled. Duplicate video IDs are rejected: choose
one explicit image per video before applying. The manifest's cover is never
sent to a video. Original video metadata/privacy/schedules remain untouched.
The batch stops on the first failure and records successful, failed and pending
entries; retrying a matching report skips successful ones. Changed images or
mappings require an inspected new plan. A checkpoint error returns the partial
report to the caller; inspect it before retrying.

This operation needs the artwork extra to validate image contents. Existing
video-thumbnail validation retains youtube3's conservative 2 MiB size policy
and 640-pixel minimum width. Google's current
[thumbnails.set reference](https://developers.google.com/youtube/data/reference/rest/v3/thumbnails/set)
lists 50 MB and approximately 50 quota units per call (checked 2026-10-30);
the library policy deliberately remains smaller for compatibility.
Python: `youtube3.thumbnail_batch.plan_thumbnail_batch(client, manifest)` and
`apply_thumbnail_batch(client, manifest, previous=None, report_path=None)`;
`ThumbnailBatchError.report` retains partial results on failure.

### Playlist cover API

```sh
youtube3 playlist cover PLAYLIST_ID --image square.png --profile mybrand
youtube3 playlist cover PLAYLIST_ID --manifest artwork/artwork.json --profile mybrand --apply
```

The manifest path selects its separate `cover`, never a video's thumbnail.
Preview checks ownership and lists existing image resources; `--apply` inserts
a missing hero image or updates the existing hero's resource ID. It never
reorders or deletes playlist items. An image/cover change after planning
requires a new preview; permission/eligibility errors are reported clearly.
Images must fully decode as square PNG/JPEG, at most 50 MiB; validation needs
the artwork extra. Google documents 1 unit for listing and 50 for insert/update.
See [insert](https://developers.google.com/youtube/data/reference/rest/v3/playlistImages/insert),
[update](https://developers.google.com/youtube/data/reference/rest/v3/playlistImages/update)
and [list](https://developers.google.com/youtube/data/reference/rest/v3/playlistImages/list).
Checked 2026-10-30 against public discovery revision 20261029: its list filter
is `parent` (the prose reference calls it `playlistId`), and the cover type is
`hero`. The client follows its bundled discovery, including media uploads for
both insert/update. `google-api-python-client>=2.201.0` is required for this
verified contract; unsupported custom/older discovery fails with an upgrade
message rather than issuing a guessed request. Account/project eligibility
still requires an owner-approved live check before milestone tagging.

Python: `client.list_playlist_images(playlist_id)` and
`client.set_playlist_cover(playlist_id, image, apply=False)`. For separate stages,
use `youtube3.playlist_cover.plan_playlist_cover` / `apply_playlist_cover`.

## DIRECT VIDEO UPLOADS

```sh
youtube3 upload episode.mp4 --title "Episode 1" --profile mybrand
youtube3 upload episode.mp4 --title "Episode 1" --profile mybrand --apply
```

Preview validates the file/metadata and reads the selected destination channel;
it constructs no upload. `--apply` starts one resumable `videos.insert` session.
Privacy is explicitly `private` unless `--privacy unlisted|public` is given.
Options include description, category ID (default 22), comma-separated tags,
made-for-kids declaration, subscriber notifications (off by default), bounded
`--retries` (0–10) and `--chunk-size` in multiples of 256 KiB (default 8 MiB).
The file must be non-empty, <=256 GiB, with a supported video-container extension;
YouTube still validates the media itself. Existing profile/OAuth selection applies;
download cookies are never used for uploads.

Retries stay inside the known resumable session. A failure while starting a
session, exhausted retries, interruption or missing final ID is an **unknown
outcome**: inspect the channel before any new upload. There is no automatic
replacement upload or durable cross-process upload resume. Session URLs and raw
API errors are never returned, logged by this workflow or saved in reports.
Progress callbacks receive `(uploaded_bytes, total_bytes)` only.

Python: `client.upload_video(file, title="Episode", apply=False, ...)` returns
the preview and, when applied, an upload result containing the video ID.
`youtube3.upload.plan_video_upload` / `apply_video_upload` expose separate stages;
`UploadError.outcome` and `.video_id` support recovery.

Contract checked 2026-10-30: [videos.insert](https://developers.google.com/youtube/data/reference/rest/v3/videos/insert)
accepts resumable media and `youtube.upload`, `youtube` or `youtube.force-ssl`
authorization (youtube3 already requests `youtube`). The current reference says
unverified API projects are not restricted to private uploads; account/project
behavior still needs an owner-approved live check. The current
[quota reference](https://developers.google.com/youtube/data/determine_quota_cost)
assigns 1 unit per insert in a separate Video Uploads bucket, default 100 calls/day.
The [resumable protocol](https://developers.google.com/youtube/data/guides/using_resumable_upload_protocol)
allows status queries/recovery within the existing session.

## PUBLISHING

Upload the video in Studio or with `youtube3 upload`, then set its metadata,
thumbnail and publishing time in one command:

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

### Recoverable publishing jobs

```sh
youtube3 publishing --file episode.mp4 --title "Episode 1" --thumbnail artwork.png --privacy public --profile mybrand
youtube3 publishing --file episode.mp4 --title "Episode 1" --thumbnail artwork.png --privacy public --profile mybrand --job job.json --apply
youtube3 publishing --resume job.json --profile mybrand --apply
```

Use `--video-id VIDEO_ID` instead of `--file` for an existing Studio upload.
A thumbnail may be a supplied file or the output of the local artwork renderer.
`--schedule ISO_TIME` keeps the video private until its future publication time.
Preview exposes upload, thumbnail, metadata and publication stages without an
upload, account write or checkpoint file. Applying a new job requires a new
`--job` path; resume uses its saved settings and channel/profile.

New media always uploads privately. The returned ID is checkpointed before
artwork, metadata or final visibility/scheduling. Each stage records pending,
running, successful, skipped or failed; uncertain uploads require recovery.
A failure after upload retains the ID. Resume skips completed stages and never
uploads again when the ID is known, even if the original media was removed.
Metadata/status updates reuse the existing publishing code and preserve
unrelated writable fields. A later stage failure stops subsequent stages.

If the process stops during upload or its ID cannot be checkpointed, inspect
the channel. The job refuses automatic reupload. Once the ID is found, use
`youtube3 publishing --resume job.json --profile mybrand --recover-video-id VIDEO_ID --apply`.
The recovered ID must belong to the selected channel. A checkpoint-write error
also prints/returns the current known ID and job state, which can be used for
explicit recovery. No credentials, raw API errors or resumable-session URLs
are stored. Checkpoints contain selected metadata and local paths: keep them
local. A failed file write before upload prevents any account write.

Python: `youtube3.publishing_job.plan_publishing_job(client, ...)`,
`apply_publishing_job(client, job, path, resume=False, recover_video_id=None)`
and `load_job(path)`. `PublishingJobError.job` and `.video_id` expose recovery
state even if saving failed. Existing `youtube3 publish VIDEO_ID` remains usable.

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
-   `upload_video`: Preview or apply a single resumable local video upload, private by default.
-   `list_playlist_images`: List a playlist's image resources, following pagination.
-   `create_playlist`: Preview or explicitly create an empty playlist, private by default, returning its resource and ID.
-   `set_playlist_cover`: Preview or explicitly apply a square local playlist-cover image.
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

## PUBLISHING CONFIGURATION

Channel/series presets are separate, explicitly selected JSON/YAML files; OAuth
profiles and credentials are never part of them. JSON works in the base install;
YAML needs `pip install "youtube3[publishing]"` (or the artwork extra).

```json
{
  "schema": "youtube3.publishing-presets.v1",
  "defaults": {"privacy": "private", "tags": ["my-series"]},
  "presets": {
    "series": {
      "profile": "mybrand",
      "expected_channel_id": "UC_REPLACE_ME",
      "variables": {"series": "My series"},
      "title_template": "{series} — Episode {episode:03d}",
      "thumbnail_template": "artwork/{stem}.png"
    }
  }
}
```

```sh
youtube3 publishing --file episode.mp4 --presets presets.json --preset series --episode 7
youtube3 publishing --file episode.mp4 --presets presets.json --preset series --episode 7 --job job.json --apply
```

Defaults are overridden by the named preset, then explicit CLI fields. Thumbnail
paths resolve beside the preset file; CLI paths resolve from the current folder.
`expected_channel_id` rejects a wrong destination before writes. Templates allow
simple variables and bounded integer formatting such as `{episode:03d}`; built-in
file variables are `stem` and `filename`, plus `episode` when given. No attribute
access, indexing, expressions or code execution. Only `_template` fields expand;
literal descriptions/titles retain braces. A literal CLI title replaces a preset
template. Unknown fields and duplicate keys fail clearly. Supported settings are
profile/expected channel, title/description/tags/thumbnail, privacy/publication
time, category, audience and retries. Resume uses the checkpoint's fixed settings.
Python: `youtube3.publishing_config.resolve_preset(path, name, overrides=..., context=...)`.

Per-video configuration extends precedence to **defaults → preset → video
settings → explicit CLI overrides**. Lists replace earlier lists; `false`, `[]`,
`""` and `null` are explicit values, never silently replaced by defaults.
`--unset FIELD` clears an inherited optional setting, e.g. `--unset privacy`
leaves a new upload private without a final visibility change. Applying still
requires an explicit CLI `--apply` and a new job path; configs cannot enable it.

```sh
youtube3 publishing --config examples/publishing/video.yaml
youtube3 publishing --config video.yaml --title "An explicit title" --unset thumbnail
youtube3 publishing --config video.yaml --job job.json --apply
```

See `examples/publishing/presets.json` and `video.yaml` for synthetic editable
examples. Paths may be absolute, start with `~`, or be relative. `file`, `presets` and artwork paths resolve relative to the file that
defines them; CLI paths use the current folder. A per-video file uses schema
`youtube3.publishing-video.v1` and accepts `file` or `video_id`, `presets`/`preset`,
`episode` and `settings`. Settings have the same validated fields as presets.
Python: `resolve_video_config(path, overrides=..., file=..., episode=...)`
returns the effective source and settings without login or account calls.

Expanded metadata settings are available in presets, video files, Python upload
and publishing plans, and the `upload`/`publishing` commands:

| Setting | CLI | Values |
|---|---|---|
| `made_for_kids` | `--made-for-kids` / `--no-made-for-kids` | true/false |
| `default_language` | `--default-language` | language tag, e.g. en-US |
| `default_audio_language` | `--default-audio-language` | default audio-track language |
| `license` | `--license` | youtube / creativeCommon |
| `embeddable` | `--embeddable` / `--no-embeddable` | true/false |
| `contains_synthetic_media` | positive / `--no-contains-synthetic-media` | true/false |
| `public_stats_viewable` | positive / `--no-public-stats-viewable` | true/false |
| `notify_subscribers` | positive / `--no-notify-subscribers` | true/false; new uploads only |
| `retries`, `chunk_size` | `--retries`, `--chunk-size` | bounded retries; chunk bytes |

Omitted metadata fields preserve existing values on updates; explicit false is
sent. Language/category/status controls are validated before writes. Publishing
jobs still upload privately and change final visibility last. Old v1 checkpoints
without the extra fields remain readable. No arbitrary API payloads are accepted.
Contracts checked 2026-10-30 against the official
[video resource](https://developers.google.com/youtube/data/reference/rest/v3/videos),
[insert](https://developers.google.com/youtube/data/reference/rest/v3/videos/insert)
and [update](https://developers.google.com/youtube/data/reference/rest/v3/videos/update)
references and bundled discovery. The audio-language field is defined in the
resource/discovery even though the method prose does not enumerate it. Actual
channel permissions, processing and eligibility need owner-approved G5.

## PUBLISHING BATCH PLANS

```sh
youtube3 publishing-batch plan examples/publishing/batch.yaml
youtube3 publishing-batch plan batch.yaml --out plan.json
```

A batch lists explicit entries with stable unique IDs, source files or existing
video IDs, episode numbers, settings, optional per-video `config` paths, and
`playlists` destinations. Nothing enumerates a directory again after planning.
Precedence is preset defaults → preset → batch settings/cadence → per-video
file settings → entry settings → CLI profile override. Relative paths use the
file defining them. Duplicate entry IDs and repeated sources are rejected.
Every job and destination playlist is preflighted for the selected channel.
A preview writes no files/account data; `--out` explicitly saves the fixed plan.

Cadence uses `schedule: {start: "2099-01-01T18:00:00+01:00", interval_minutes: 1440}`.
The start requires an explicit UTC offset; intervals mean elapsed minutes, not
wall-clock calendar days across daylight-saving changes. Results are fixed UTC
timestamps. Per-video `publish_at` overrides cadence, so individual calendar/DST
choices can be specified explicitly. Omitted schedules leave new media private.
Thumbnails may refer to supplied files or earlier local-renderer outputs.

Python: `publishing_batch.resolve_batch(path)` resolves locally;
`plan_batch(client, entries)` performs read-only preflight;
`save_plan`/`load_plan` preserve the fixed mapping. Playlist membership uses a
video-filtered read before insertion and can perform read-only recovery for
uncertain earlier writes. Contracts checked 2026-10-30 against official
[playlistItems.list](https://developers.google.com/youtube/data/reference/rest/v3/playlistItems/list)
and [insert](https://developers.google.com/youtube/data/reference/rest/v3/playlistItems/insert).
No playlist reordering is performed.

## PUBLISHING QUEUES

```sh
# Preview execution without creating state or logging in:
youtube3 publishing-batch run plan.json --queue queue.json
# Execute the saved mapping, with a durable queue and upload ledger:
youtube3 publishing-batch run plan.json --queue queue.json --apply
youtube3 publishing-batch status queue.json
youtube3 publishing-batch pause queue.json
youtube3 publishing-batch resume queue.json --apply
# Retry only a selected failed entry/stage:
youtube3 publishing-batch retry queue.json --entry episode-7 --stage thumbnail --apply
```

The queue reuses per-video publishing jobs. OS-backed queue and channel-ledger
locks prevent concurrent runners and release automatically on process exit.
Pause is a separate request file: the runner checks it before each stage/write,
so an active upload chunk/session finishes before stopping. `resume` clears the
pause request; completed entries/stages stay complete. `--limit N` runs at most
N selected entries; `--continue-on-error` permits later independent entries to
run after a failure. `retry --entry ID` resumes that failed job and its remaining
stages; optional `--stage` verifies the recorded failure matches the request.
Playlist membership completes before final public visibility/scheduling.
Uncertain playlist insertions are checked read-only on retry, never blindly
inserted again.

New upload files are SHA-256 fingerprinted, which can take time for large media.
A default per-channel ledger lives in the config folder's `publishing/` directory,
separate from OAuth profiles; `--ledger FILE` explicitly chooses another ledger
when creating a queue. Share that file across batches to share duplicate history.
Duplicate contents within a batch are rejected before upload. A renamed file
already recorded as uploaded is reported as `duplicate` with its ID and is not
uploaded or used to silently change the old video's metadata. Reusing an ID for
new metadata is an explicit recovery choice. Pending/unknown upload reservations
block automatic uploads, including when a job checkpoint is missing. Changed
media requires a new plan. Known-ID resumes do not need the original video file.

After inspecting an uncertain outcome, choose one explicit recovery action:

```sh
youtube3 publishing-batch recover queue.json --entry episode-7 --video-id RECOVERED_ID --apply
# Only after confirming no video was created:
youtube3 publishing-batch recover queue.json --entry episode-7 --confirm-not-uploaded --apply
# Only after confirming an uncertain membership is absent:
youtube3 publishing-batch recover queue.json --entry episode-7 --missing-playlist PLAYLIST_ID --apply
youtube3 publishing-batch resume queue.json --apply
```

Recovered IDs must belong to the selected channel. A known uploaded ID cannot
be replaced or reset to pending. Failures after upload retain the ID in the job
checkpoint/ledger; persistence errors expose known IDs in the returned queue.
Reports contain selected metadata, local paths, hashes, IDs and stage states;
no OAuth credentials, raw API errors or resumable-session URLs are stored.
New queues and saved plans preserve existing files. Keep their checkpoint files,
`*.jobs` directory and shared ledger together for recovery; locks do not require
manual stale-lock deletion. No account write occurs without CLI `--apply`.

Python: `publishing_queue.initialize_queue(plan, path, ledger_path=...)`,
`run_queue(client, path, resume=False, retry=False, select=None, stage=None, limit=None)`,
`request_pause(path)`, `status(path)` and `recover_entry(...)`.
`QueueError.queue` exposes recovery state. Per-video `apply_publishing_job` also
accepts optional `before_stage`/`after_stage` callbacks; returning false from the
former checkpoints a pause before that stage, and the latter runs after its
successful checkpoint. Callbacks are Python-only, never loaded from config.
