> Guidance for Claude Code. This repository runs in Claude Code mode only; it
> has no `AGENTS.md`. The shared principles and the verdict protocol are in
> [`PRINCIPLES.md`](PRINCIPLES.md), amended for this project by the owner
> decisions in the project slot below. **Read both before implementing.**

# The Claude Code mode

This file records the Claude-specific process and the project slot.

## The process

- Claude does the work itself, the proposal and the implementation, on a
  branch, and opens a pull request against `master` on
  `diegoami/youtube3`.
- Claude **does not spawn its own reviewer**. For every pull request, Claude
  verifies the work itself and says how in the PR: each gate it ran, its
  result, and what it would have caught had the code been wrong
  (`PRINCIPLES.md`, the six gates disciplines).
- A finding Claude disagrees with goes to the owner, not around the reviewer.
- Merging is `merge: auto`; the conditions are under **Merging** below.

### Milestones and the independent review

*Reviewer: if a review-handoff prompt brought you here, that prompt defines
your job; this file is the standard you review against.*

A **milestone is a point in time**: an annotated tag `vX.Y.Z` on `master`.
It is not a branch, a pull request or a proposal. The independent review
happens **per milestone, never per PR**: proposals and pull requests get no
review prompt, and nothing waits for a review between milestones.

1. **Calling one.** The owner calls a milestone, or Claude proposes one when
   a coherent set of work has landed: a roadmap group, a breaking change,
   anything meant for a PyPI release.
2. **The milestone issue.** Claude opens an issue labelled `milestone`,
   titled `Milestone vX.Y.Z`, with the candidate commit on `master` (full
   SHA), the previous milestone tag, the pull requests merged since, the
   gate results on the candidate (CI and G1–G4), and the owner's G5 result
   when an API call changed.
3. **The review.** Claude gives the owner one prompt (the `review-handoff`
   skill) to run in a **different model**, in whatever tool the owner picks
   (Codex, DeepSeek, OpenCode, or another), in a fresh session every time.
   The reviewer checks out the candidate SHA, reviews
   `git diff <previous tag>..<candidate>` and follows it into any file it
   touches.
4. **BLOCK.** The findings are fixed in ordinary PRs; the candidate moves to
   the new `master` commit, and Claude gives a re-review prompt without being
   asked. The round ceiling in `PRINCIPLES.md` applies: a third round that
   does not end in AGREE goes to the owner.
5. **AGREE.** Claude creates the annotated tag on **exactly the reviewed
   SHA**, never a later commit, pushes it, and posts the completion note on
   the milestone issue. Work merged after the candidate belongs to the next
   milestone. G5, the owner's live check, happens before the tag whenever
   the milestone changes an API call. Uploading to PyPI stays the owner's.
6. The owner may tag without a review; the milestone issue records that.

The baseline is `v1.2.5` on `56e351b`, the last commit before the 2026
revival (its `setup.py` says 1.2.5, as published on PyPI). The older tag
`1.1.0` stays as it is.

The reviewer posts to GitHub itself, and nothing is pasted back:

- **one issue per reproduced finding**, labelled `review` plus a category
  label (`bug`, `robustness`, `tests`, `design`, `cleanup`,
  `documentation`), linking back to the milestone issue and the SHA;
- **always one verdict comment** on the milestone issue: AGREE, or BLOCK when
  any finding is MUST-FIX; the SHA reviewed, the issues it opened, what it
  checked and found clean. A review that finds nothing still leaves a
  record.

Severities: **MUST-FIX** (fixed before the tag), **SHOULD**, and **OUT OF
SCOPE** (not caused by the milestone's changes). When the owner says the
review is in: read it from GitHub, reproduce each finding before acting on
it, and fix it (`Fixes #n` in the PR) or rebut it with evidence on the
issue. Owner decisions go to the owner with a recommended default, not into
the code.

### Merging

Claude merges a pull request itself (`gh pr merge --merge --delete-branch`)
when all of these hold, and records in the PR which ones it checked:

1. every gate in the gates table that the diff can affect is green **on the
   PR's head**, with the output summarised in the PR body, and CI is green
   on that head;
2. no open MUST-FIX issue names the PR;
3. the owner has not asked to hold it.

Process changes (`PRINCIPLES.md`, `CLAUDE.md`, `.claude/**`) merge on the
same conditions (owner decision 4). Tags follow the milestone steps above;
uploading to PyPI is the owner's, always.

## Project slot

<!-- SLOT:BEGIN -->

- **product:** youtube3 — a Python wrapper over the YouTube Data API v3,
  published on PyPI as `youtube3` (1.2.5, last released 2023). Its point is
  the **convenience operations** the raw API lacks, for the owner's own
  account: copy or move a range of a playlist, publish a whole playlist, like
  and subscribe, check region blocks, update snippets and thumbnails. It is
  being revived in 2026 to manage the owner's likes, build a landing page of
  them, and help with publishing (thumbnails, metadata, scheduling); the
  queue is `ROADMAP.md`.
- **paths to inspect:** `youtube3/` (the package), `tests/` (offline unit
  tests), `samples/` (one runnable script per operation), `README.md`,
  `pyproject.toml` (metadata, dependencies, pytest and ruff config),
  `ROADMAP.md`.
- **the canonical source:** `youtube3/youtube_client.py` for behaviour. The
  method list in `README.md` mirrors it and is updated in the same change.
  `samples/` are examples, not API. `build/`, `dist/` and `*.egg-info/` are
  generated by packaging: never edit or cite them.
- **paths to normally ignore:** `samples/test/*.json` — captured API
  responses kept as example data (small; open one only when a test needs
  it). `liked*.json`, `unliked-*.json`, `reliked-*.json`, `liked*.html` —
  the owner's exported likes, the undo logs of rating runs and the pages built
  from them: personal data, ignored by git; read one only to check an export's shape or count, and never paste
  its contents into an issue or a PR. `build/`, `dist/`, `.eggs/`, `*.egg-info/`, `__pycache__/` —
  generated. `.idea/` — editor state.
- **never read or echo:** `client_secrets*.json` anywhere (the samples expect
  `samples/client_secrets.json`); `youtube.dat` (the oauth2client token
  store) and `token.json` or any other saved OAuth token, including the
  profiles in `~/.config/youtube3/profiles/` (F-8); Google Takeout
  exports (`Takeout/`, `takeout-*.zip`) and what is imported from them
  (`history*.json`, `history*.html`): Claude runs the importer, builds the
  page and looks at it only when the owner asks (owner decision on #37,
  changed by the owner on 2026-09-25: "you can export it too and show it to
  me, just do not do any destructive operation"), never pastes their
  contents into an issue or a PR, and does nothing destructive with them; `~/.pypirc` and PyPI
  tokens; `.env*`. Never print an access or refresh token, an `Authorization` header
  or an API key, not even in test output.
- **merge:** auto — the conditions are in **Merging** above.
- **design:** none — see owner decision 3.
- **the gates table:**

  | gate | command | covers | runs | repeats | failure model |
  |---|---|---|---|---|---|
  | G1 compile | `python -m compileall -q youtube3 samples tests` | every module parses, samples included (they have no tests) | every PR, CI | 1 | deterministic |
  | G2 lint | `ruff check` | the `pyproject.toml` rule set (`E4 E7 E9 F B`) over `youtube3/`, `samples/`, `tests/` | every PR, CI | 1 | deterministic |
  | G3 unit tests | `pytest -q` | the client's requests and results over canned responses (`tests/conftest.py`: the bundled discovery document, `HttpMockSequence`, no network); known bugs pinned as strict `xfail` | every PR, CI | 1 | deterministic, offline; a failure is a real failure |
  | G3b page logic | `node --test "tests/page/*.test.cjs"` (Node 24) | the landing page's search, channel filter, sorts and counts in `youtube3/page_assets/page.js`, and that it builds elements without ever parsing markup (a stub `document` that refuses `innerHTML`, #35) | every PR touching the page, CI | 1 | deterministic, offline |
  | G4 package | `python -m build`, `twine check --strict`, install the wheel in a fresh venv, `import youtube3` outside the checkout, and build a page from it | the metadata, the declared dependencies resolve, the package imports from an install, and the page assets ship in the wheel | every PR, CI | 1 | deterministic given the package index; a network error is re-run once and recorded |
  | G5 live | the affected `samples/*.py` against the owner's account | real API behaviour: OAuth, quota, what the owner would see on YouTube | by the owner, before a milestone tag whose changes touch an API call — it writes to a real account | 1 | a live service: a failure is reproduced once before it is believed |

  CI (`.github/workflows/ci.yml`) runs G1–G4 on Ubuntu with Python 3.11 and
  3.14, and G1–G3b on Windows with 3.14 (the token file's ACL, #15), for
  every pull request and every push to `master`; a red CI does not merge. A
  change to the page is also opened in a headless browser on the owner's real
  export before its PR (the checks and screenshots stay local: the export is
  personal data).
  Locally, install with `pip install -e ".[dev]"` and run the same commands;
  `python -m build` leaves `dist/` and `*.egg-info/`, both ignored.
- **conventions:**
  - English for code, comments, docs, commits, and command-line output.
    Commit subjects are imperative, sentence case, no prefix (as in the
    existing history).
  - Python **3.11+** (owner decision 1); licensed BSD-3-Clause (owner
    decision 5).
  - The base client is Google's `google-api-python-client`; a new runtime
    dependency is named in the PR with its reason.
  - `YoutubeClient` is public on PyPI: a change that breaks an existing
    method's signature or return shape bumps the major version and says so.
  - Anything that writes to the account in bulk (unlike, delete from a
    playlist, change privacy) gets a dry-run mode that lists what it would do.
  - **Decided, and not to be re-opened:**
    - *Watch history cannot be read or modified through the API.* Google
      removed history from the Data API in 2016; `relatedPlaylists` no longer
      carries `watchHistory`. History features are read-only, from a Google
      Takeout export. Deleting history is done on myactivity.google.com;
      browser automation for it is out (fragile, against YouTube's terms).
    - *`search.list(relatedToVideoId=…)` is gone* (removed in 2023), so
      related videos cannot be fetched; *`activities.list(mine=True)`* returns
      the owner's own activity, not recommendations.
    - *python-youtube (`pyyoutube`) was considered and not adopted*
      (2026-09-23): it covers the raw API but none of the convenience
      operations, and its OAuth is a manual paste with no token storage.
    - *yt-dlp with browser cookies (`:ythistory`) is not used for the
      history* (owner, 2026-09-25: "yt-dlp is not viable for a library I
      want to distribute"): the cookies are the whole Google login, reading
      the site this way is against YouTube's terms, and it gives no watch
      times. The history comes from a Google export only.
    - *`thumbnails.set` takes a local file, not a URL* (max 2 MB), and needs a
      phone-verified channel; videos **uploaded** through an unaudited API
      project are locked private, so uploads happen in Studio and the API
      does the metadata, thumbnail and publishing.
  - **Open work:** `ROADMAP.md`, and GitHub issues on `diegoami/youtube3`.
- **owner decisions, 2026-09-23** (each an owner-decision amendment to
  `PRINCIPLES.md` for this project):
  1. **Python 3.11+.** First 3.10+; raised to 3.11 by the owner on
     2026-09-23 because `google.api_core` stops releasing for 3.10 after its
     end of life on 2026-10-04.
  2. **Review:** Claude Code only, with an **independent review at
     milestones**, as in discola-web and Geoclick2027. On 2026-09-23 the
     owner defined a milestone as a **tag**, a point in time, not a PR; the
     tag waits for the review, pull requests do not. Claude creates the tag
     after AGREE. This replaces the fresh-context review of every
     non-trivial change: between milestones, Claude's self-verification in
     each PR is the record. The verdict protocol
     of `PRINCIPLES.md` (target proof, rounds, materiality, owner decisions,
     defect path) governs the milestone reviews.
  3. **Records live on GitHub.** The proposal issue is the design record; the
     milestone issue, its verdict comment and the `review` issues are the
     review record; there are no `design/` or `reviews/` directories. The completion note is a comment
     on the proposal issue when its PR merges. Implementation does not wait
     for a proposal review: the owner's go on the proposal starts the branch.
  4. **`merge: auto`**, with the conditions in **Merging** above. Unlike
     `PRINCIPLES.md`'s ("review clean plus gates green"), a pull request
     never waits for a review; the review gates the milestone tag instead.
     On 2026-09-23 the owner ruled that a green PR is Claude's to merge,
     process changes included. PyPI uploads stay with the owner.
  5. **License: BSD-3-Clause**, with a `LICENSE` file, replacing the bare
     "BSD License" published up to 1.2.5 (#7). Chosen by the owner,
     2026-09-23.
- **provenance:** adopted from harness_template release `r4` (tag commit
  `39c29e3`), taking the post-release wording fixes up to `d93c257`, on
  2026-09-23. Taken: `PRINCIPLES.md` (the conservative floor rewritten for
  this repository's paths), this file, `ROADMAP.md`. Not taken: `AGENTS.md`
  (Claude only), `PLAN.md`, `design/`, `reviews/`, `verification/` (see
  decisions 2 and 3). The milestone review and the `review-handoff` skill are
  adapted from Geoclick2027 (`CLAUDE.md` §3a, 2026-09-23).

<!-- SLOT:END -->
