# Roadmap — requests

> How the project grows. The owner writes requests; the implementer shapes them; an
> accepted request is one proposal, one branch and one pull request
> ([`AGENTS.md`](AGENTS.md)).

## The queue

| id | request | status | notes |
|---|---|---|---|
| F-23 | "could we add a playlist creation in our library ?" | implemented | #164: private-by-default client method and `playlist create` CLI, preview/apply, destination channel and created ID, offline request/CLI checks. Live G5 and milestone review remain separate. |
| F-1 | "Would like to revive this repo, tell me if we can make it usable" | landed | Proposal #5, PR #6. The gates first: `pyproject.toml` (Python 3.10+, raised to 3.11+ in #8), pytest with `googleapiclient.http.HttpMock`, ruff, a GitHub Actions workflow; `.gitignore` for `client_secrets*.json`, `token.json`, `*.egg-info/`. |
| F-2 | "Would like to revive this repo, tell me if we can make it usable" | landed | Proposal #9, PR #10. Login through `google-auth-oauthlib` with a refreshed, stored token instead of `oauth2client`/`sample_tools`; remove the related-videos and recommended calls; fix the playlist range counter in `copy_to_playlist`/`delete_from_playlist` (flips F-1's strict `xfail` tests), the logged id, `maxCount` yielding one page more than asked (F-1's `test_iterate_videos_in_playlist_max_count_current_behaviour` pins it and changes with the fix), `maxResults=50`, `ChannelNotFoundException(Exception)`. Depends on F-1. |
| F-3 | "the liked" — "The convenience operations is what I missed" | landed | Proposal #20, PRs #21 and #22. Export the `LL` playlist to JSON, incrementally; bulk unlike through `videos.rate(rating="none")` by channel, date or id, with a dry run. Depends on F-2. |
| F-4 | "make a landing page with liked" | landed | Proposal #29, PR #30. A static page built from F-3's export: thumbnails, titles, channels, dates, search. Where it is hosted is an open question. Depends on F-3. |
| F-5 | "help with publishing, such setting a thumbnail" | landed | Proposal #33, PR #34. One command: thumbnail from a local file, title and description, publish now or schedule (`publishAt`). Uploads stay in Studio (`CLAUDE.md`, decided). Depends on F-2. |
| F-6 | "modify the history" | removed | Proposal #37, PR #38, reshaped by the owner: "we can get an history and get some links or ways to enable user to work on the history". Import a Takeout export read-only, a history page, links to where Google lets it be changed. Acting on history through the API (like, playlist, subscribe) is F-7. Removed by the owner's decision, #62. |
| F-7 | "get some links or ways to enable user to work on the history" — "start F-7" | removed | Proposal #39, PR #40. Like, add to a playlist, or subscribe from a history selection, as a dry run unless `--apply`, with an undo log. Depends on F-6. Removed by the owner's decision, #62. |
| F-8 | "Well the thing that I miss, I have several \"brands\", I need to manage them separately" — "ok can you simplify the takeout workflow for me too ?" | landed | Proposal #55. One profile per channel (brand account), checked on every run; files per profile; the newest Takeout found in Downloads, one command for the history page, a warning when an export is another account's. Its Takeout parts (the newest export found in Downloads, `history_page.py`, the wrong-account warning) were removed with #62; the profiles stay. |
| F-9 | "ok can you simplify the takeout workflow for me too ?" | dropped | Fetch the history without Takeout through the Data Portability API. Trial on 2026-09-25: consent for a brand channel (CaramellaLynx) accepted, with time-based (repeatable) access; the export of `myactivity.youtube` also carries the search history, and it was still in progress after about 11 hours, when the owner stopped the trial and its consent was deleted. Worth reopening only if an export limited to a start date proves quick. yt-dlp with cookies was ruled out (CLAUDE.md). Dropped with the history features, #62. |
| F-10 | "why do we not ship the samples, and do they still work ?" — "ok do as you suggest" | landed | Proposal #86, PR #91: one `youtube3` command that `pip install` provides (profiles, likes, publish, playlists, videos, subscriptions), a dry run for everything that writes, `samples/` removed, and `youtube3 setup` for client secrets. |
| F-11 | "But would not these be kind of useful is somewhat generalized" (blogspotapi) — "Retire them and park the ideas" | parked | From the retired blogspotapi (archived 2026-09-26): scan HTML, Markdown or a blog export (Blogger, WordPress) for embedded YouTube videos and report the ones deleted, private, region-blocked or not embeddable, using `verify_video`; fixing a post comes later, as a dry run first. Parked by the owner: no current use. Best built as a command after F-10. |
| F-12 | "But would not these be kind of useful is somewhat generalized" (amaraapi) — "Retire them and park the ideas" | parked | From the retired amaraapi (archived 2026-09-26), through YouTube's own captions API instead of Amara: list, download and upload the captions of your own videos (upload 400 quota units). Parked by the owner: no current use. |
| F-13 | "get all videos in channel" | landed | Proposal #92, PR #93: `youtube3 channel videos` lists the signed-in profile's uploads (private and unlisted included) to the console and a JSON export. Owner G5 read-only check passed, including a fresh-wheel run outside the checkout. |
| F-14 | "What about adding features for download using youtube-dlp or comparable libraries ?" — "ok let us do a POC" | landed | Proposal #101, PR #102: optional `youtube3[download]`, one public video, output folder, quality limit and offline dry run. Playlist support follows in F-15; authenticated downloads remain deferred. |
| F-15 | "yes do it, review only when reaching a milestone, do you have the review release skill ?" | landed | Proposal #103, PR #102: public playlist downloads with a default preview, 1-based inclusive ranges, ordered filenames and a completed-ID archive shared with single-video downloads. Review remains at milestones. |
| F-16 | "ok continue with other fetaures" | landed | Proposal #104: audio-only downloads and conversion, read-only format previews, selected subtitles/automatic captions and opt-in JSON metadata/thumbnail sidecars. Separate default archives for audio modes. Review remains at milestones. |
| F-17 | "resume" (from checkpoint #106) | landed | Proposal #107: optional playlist continuation, checkpointed JSON results and offline previews/retries of failed IDs with their original settings and positions. Review remains at milestones. |
| F-18 | "cotinue" | landed | Proposal #109: optional media bandwidth cap and HTTP/fragment retry counts, displayed in previews and preserved through batch reports/retries. Existing reports retain default settings. Review remains at milestones. |
| F-19 | "continue" | landed | Proposal #111: exact stream IDs or a video-only/audio-only pair, separate filenames/default archives, FFmpeg merge checks and preserved choices in reports/retries. Existing reports remain readable. Review remains at milestones. |
| F-20 | "how do we solve the issue with cookies and bot detection" — "ok do it" | landed | Proposal #119: extraction pacing, stopping batches on rate limits/bot challenges, and explicit cookie-file/browser/profile access. Cookie access is transient; reports retain pacing and require cookies again when retrying a cookie-enabled run. No live checks or PO-token integration. |
| F-21 | "for the next release we need to add methods for publishing videos and creating / modifying thumbnalis and generate thumbnails for playlist" | landed | Request #127: direct video-file uploads, publishing methods and thumbnail generation/editing, reusing `diegoami/lynxupercluster_thumbnailgenerator` and artwork from `diegoami/lynxsupercluster_thumbnails`. Owner confirmed both per-video thumbnails and a playlist cover, and explicitly added direct uploads. Implemented as #129–#134: local rendering, stable playlist manifests, checkpointed thumbnail application, playlist-cover APIs, single-session uploads and recoverable publishing jobs. Owner decision 7 in AGENTS.md amends the former Studio-only scope; owner-approved G5 and independent milestone review remain release gates. |

| F-22 | "ok do we have a tasks to configure upload of my videso to my channel with max flexibility" — "ok do it" | landed | Parent #145; #146 presets, #147 per-video configuration, #148 expanded metadata, #149 batch plans and #150 queue/recovery/duplicate protection. Existing F-21 jobs/uploader are reused; no live account writes authorized. |

## Statuses

`requested` → `accepted` → `in progress` → `in review` → `landed`; plus
`parked` and `refused`. **The owner accepts, parks or refuses**, and the
reason is recorded; the implementer sets the middle states.

## How to request

Add one row to the table, in your own words — or say it in a session ("add to
the roadmap: …") and the implementer appends the row and stops. **A request is not a
request to implement**: the shaping still happens, and the original wording
is quoted verbatim in the block and never silently reworded.

## The block, written when a request is accepted

```
### F-N — <title>
- **Original request:** "<verbatim>"
- **Value:** why this matters to the owner
- **Scope:** what will exist after it lands
- **Done when:** the runnable checks
- **Out of scope:** the temptations deferred, so they are recorded not lost
- **Depends on:** other requests, or none
- **Open questions:** owner decisions marked as such
```

The block is posted as a GitHub issue labelled `proposal`, and the
implementing PR says `Closes #n`. The independent review comes later, at the
milestone tag that includes the request (`AGENTS.md`).

## The implementer's job

- **Shape** a request when it is picked up: value, scope, done-when,
  out-of-scope, dependencies, open questions, recorded as the block above.
- **Size it to one pull request.** Split before starting if it does not fit;
  never let a task grow while in flight.
- Take the **first unblocked accepted** request when told "do the next roadmap
  item", and stop after it.
- Never implement an unshaped request; never set an owner status; never edit
  the original wording.

## Latitude inside a request

The implementer may choose names, the command-line shape, the page's look and the
prose, and records what it chose so the choice is visible and reversible. It
does not change **the intent of the request**, **scope**, **the done-when and
the gates** (extendable with the reason recorded, never weakened), **owner
decisions**, or the public API of `YoutubeClient` (`AGENTS.md`,
conventions).
