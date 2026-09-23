# Roadmap — requests

> How the project grows. The owner writes requests; Claude shapes them; an
> accepted request is one proposal, one branch and one pull request
> ([`CLAUDE.md`](CLAUDE.md)).

## The queue

| id | request | status | notes |
|---|---|---|---|
| F-1 | "Would like to revive this repo, tell me if we can make it usable" | landed | Proposal #5, PR #6. The gates first: `pyproject.toml` (Python 3.10+, raised to 3.11+ in #8), pytest with `googleapiclient.http.HttpMock`, ruff, a GitHub Actions workflow; `.gitignore` for `client_secrets*.json`, `token.json`, `*.egg-info/`. |
| F-2 | "Would like to revive this repo, tell me if we can make it usable" | landed | Proposal #9, PR #10. Login through `google-auth-oauthlib` with a refreshed, stored token instead of `oauth2client`/`sample_tools`; remove the related-videos and recommended calls; fix the playlist range counter in `copy_to_playlist`/`delete_from_playlist` (flips F-1's strict `xfail` tests), the logged id, `maxCount` yielding one page more than asked (F-1's `test_iterate_videos_in_playlist_max_count_current_behaviour` pins it and changes with the fix), `maxResults=50`, `ChannelNotFoundException(Exception)`. Depends on F-1. |
| F-3 | "the liked" — "The convenience operations is what I missed" | landed | Proposal #20, PRs #21 and #22. Export the `LL` playlist to JSON, incrementally; bulk unlike through `videos.rate(rating="none")` by channel, date or id, with a dry run. Depends on F-2. |
| F-4 | "make a landing page with liked" | requested | A static page built from F-3's export: thumbnails, titles, channels, dates, search. Where it is hosted is an open question. Depends on F-3. |
| F-5 | "help with publishing, such setting a thumbnail" | requested | One command: thumbnail from a local file, title and description, publish now or schedule (`publishAt`). Uploads stay in Studio (`CLAUDE.md`, decided). Depends on F-2. |
| F-6 | "modify the history" | requested | **Not possible through the API** (`CLAUDE.md`, decided). The closest in scope: import a Google Takeout export read-only and show it on F-4's page. The owner accepts that reduced scope, or parks the request. |

## Statuses

`requested` → `accepted` → `in progress` → `in review` → `landed`; plus
`parked` and `refused`. **The owner accepts, parks or refuses**, and the
reason is recorded; Claude sets the middle states.

## How to request

Add one row to the table, in your own words — or say it in a session ("add to
the roadmap: …") and Claude appends the row and stops. **A request is not a
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
milestone tag that includes the request (`CLAUDE.md`).

## Claude's job

- **Shape** a request when it is picked up: value, scope, done-when,
  out-of-scope, dependencies, open questions, recorded as the block above.
- **Size it to one pull request.** Split before starting if it does not fit;
  never let a task grow while in flight.
- Take the **first unblocked accepted** request when told "do the next roadmap
  item", and stop after it.
- Never implement an unshaped request; never set an owner status; never edit
  the original wording.

## Latitude inside a request

Claude may choose names, the command-line shape, the page's look and the
prose, and records what it chose so the choice is visible and reversible. It
does not change **the intent of the request**, **scope**, **the done-when and
the gates** (extendable with the reason recorded, never weakened), **owner
decisions**, or the public API of `YoutubeClient` (`CLAUDE.md`,
conventions).
