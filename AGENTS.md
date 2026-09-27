> Guidance for OpenCode. Claude Code uses [`CLAUDE.md`](CLAUDE.md); the shared
> principles and verdict protocol are in [`PRINCIPLES.md`](PRINCIPLES.md).
> **Read both before implementing.**

# The OpenCode mode

This file records the OpenCode-specific process and the complete project slot.
The owner decisions below are authoritative for this repository.

## Roles and assignment

| role | assignment |
|---|---|
| implementer | OpenCode, DeepSeek V4.1 Flash |
| reviewer | a different model family per milestone: Claude Code or GPT-6 Luna in OpenCode |

- The implementer writes changes on a branch, opens the pull request, verifies
  the affected gates, and signs GitHub records and authored documents
  `— Implementer (OpenCode, DeepSeek V4.1 Flash)`.
- The reviewer is chosen by the owner and runs the
  [`review-handoff`](.claude/skills/review-handoff/SKILL.md) prompt in a fresh
  session. The implementer never reviews its own work. The reviewer checks a
  milestone as a whole, not an individual pull request, and signs its own
  verdict.
- The invariant is the different model family from the implementer. The two
  allowed reviewer choices are current assignments, not a relaxation of that
  invariant.

## Change process

- Every change is made on a branch and submitted in a pull request against
  `master` on `diegoami/youtube3`.
- OpenCode does not start F-10 (#86), close PRs #1 or #2, or run live checks
  until the owner explicitly says what is next.
- The owner records proposals, milestones and reviews on GitHub. There are no
  `design/` or `reviews/` folders in this project.
- This project has `design: none`: there is no design stage. The review stage
  is the independent milestone review described below.
- A process or harness change is non-trivial and follows this same branch,
  pull-request and milestone-review process.
- A reviewer finding is reproduced before it is fixed or rebutted. A finding
  that remains disputed goes to the owner rather than around the reviewer.
- Before any live check, ask the owner. Read-only runs and dry runs are fine;
  anything that writes to the owner's YouTube account needs explicit approval.

## Milestones and independent review

A milestone is an annotated tag `vX.Y.Z` on `master`, a point in time. It is
not a branch or pull request. Pull requests do not wait for review; the tag
does.

1. The owner calls a milestone, or OpenCode proposes one for a coherent set of
   work, a breaking change or a PyPI release.
2. OpenCode opens an issue labelled `milestone`, titled `Milestone vX.Y.Z`,
   containing the candidate full SHA on `master`, previous milestone tag, pull
   requests since it, gate results, CI, G5 when an API call changed, and owner
   decisions since the previous tag.
3. OpenCode gives the owner one prompt from
   `.claude/skills/review-handoff/SKILL.md` to run in a fresh session of Claude
   Code or GPT-6 Luna. The reviewer checks out the candidate SHA and reviews
   `git diff <previous tag>..<candidate>` plus every touched dependency.
4. A BLOCK is fixed in ordinary pull requests. The candidate moves to the new
   `master` SHA and OpenCode gives an unasked re-review prompt. The round
   ceiling in `PRINCIPLES.md` applies; a third round without AGREE goes to the
   owner.
5. On AGREE, OpenCode creates the annotated tag on exactly the reviewed SHA,
   pushes it, and posts the completion note on the milestone issue. Work merged
   after that candidate belongs to the next milestone. G5 happens before the
   tag whenever an API call changed. PyPI uploads always remain the owner's.
6. The owner may tag without review; the milestone issue records that.

The baseline is `v1.2.5` on `56e351b`, the last commit before the 2026
revival (its `setup.py` says 1.2.5, as published on PyPI). The older tag
`1.1.0` stays as it is.

The reviewer posts to GitHub itself: one issue per reproduced finding, labelled
`review` plus a category (`bug`, `robustness`, `tests`, `design`, `cleanup`, or
`documentation`), and one verdict comment on the milestone issue. Findings are
MUST-FIX, SHOULD, or OUT OF SCOPE. The review-handoff skill defines the exact
posting format and signature.

## Merging

Merge is `auto`. OpenCode merges a pull request itself with
`gh pr merge --merge --delete-branch` only when all conditions hold:

1. Every gate the diff can affect is green on the pull request head, its output
   is summarised in the PR body, and CI is green on that head.
2. No open MUST-FIX issue names the pull request.
3. The owner has not asked to hold it.

The milestone review is not a pull-request merge condition; it gates the tag.
The PR body records the gates, deliberate-break verification, and merge checks.

## Project slot

<!-- SLOT:BEGIN -->

- **product:** youtube3 — a Python wrapper over the YouTube Data API v3,
  published on PyPI as `youtube3` (2.6.2, released 2026-09-26). Its point is
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
  responses kept as example data (small; open one only when a test needs it).
  `liked*.json`, `unliked-*.json`, `reliked-*.json`, `liked*.html` — the
  owner's exported likes, undo logs and pages built from them: personal data,
  ignored by git; never paste their contents into an issue or PR.
  `build/`, `dist/`, `.eggs/`, `*.egg-info/`, `__pycache__/` — generated.
  `.idea/` — editor state.
- **never read or echo:** `client_secrets*.json` anywhere (the samples expect
  `samples/client_secrets.json`); `youtube.dat` (the oauth2client token
  store); `samples/token.json` or any other saved OAuth token, including the
  profiles in `~/.config/youtube3/profiles/`; Google Takeout exports
  (`Takeout/`, `takeout-*.zip`) and the files once imported from them
  (`history*.json`, `history*.html`); `~/.pypirc` and PyPI tokens; `.env*`;
  any `liked*`, `history*`, `unliked-*`, or `reliked-*` file. Never print an
  access or refresh token, an `Authorization` header or an API key, including
  in test output.
- **merge:** auto — the conditions are under **Merging** above.
- **design:** none — see owner decision 3.
- **milestones:** annotated `vX.Y.Z` tags on `master`; the milestone issue and
  its GitHub review issues/comments are the release record.
- **the gates table:**

  | gate | command | covers | runs | repeats | failure model |
  |---|---|---|---|---|---|
  | G1 compile | `python -m compileall -q youtube3 samples tests` | every module parses, samples included (they have no tests) | every PR, CI | 1 | deterministic |
  | G2 lint | `ruff check` | the `pyproject.toml` rule set (`E4 E7 E9 F B`) over `youtube3/`, `samples/`, `tests/` | every PR, CI | 1 | deterministic |
  | G3 unit tests | `pytest -q` | the client's requests and results over canned responses (`tests/conftest.py`: the bundled discovery document, `HttpMockSequence`, no network); known bugs pinned as strict `xfail` | every PR, CI | 1 | deterministic, offline; a failure is a real failure |
  | G3b page logic | `node --test "tests/page/*.test.cjs"` (Node 24) | the landing page's search, channel filter, sorts and counts in `youtube3/page_assets/page.js`, and that it builds elements without ever parsing markup (a stub `document` that refuses `innerHTML`, #35) | every PR touching the page, CI | 1 | deterministic, offline |
  | G4 package | `python -m build`, `twine check --strict`, install the wheel in a fresh venv, `import youtube3` outside the checkout, and build a page from it | metadata, dependencies, installed import and shipped page assets | every PR, CI | 1 | deterministic given the package index; a network error is re-run once and recorded |
  | G5 live | the affected `samples/*.py` against the owner's account | real API behaviour: OAuth, quota, and what the owner would see on YouTube | by the owner, before a milestone tag whose changes touch an API call — it writes to a real account | 1 | a live service: a failure is reproduced once before it is believed |

  CI (`.github/workflows/ci.yml`) runs G1–G4 on Ubuntu with Python 3.11 and
  3.14, and G1–G3b on Windows with 3.14, for every pull request and push to
  `master`; a red CI does not merge. A change to the page is also opened in a
  headless browser on the owner's real export before its PR; checks and
  screenshots stay local because the export is personal data. Locally, install
  with `pip install -e ".[dev]"`; `python -m build` leaves ignored artifacts.
- **conventions:**
  - English for code, comments, docs, commits and command-line output.
    Commit subjects are imperative, sentence case, without a prefix (as in
    the existing history).
  - Python **3.11+**; licensed BSD-3-Clause.
  - The base client is Google's `google-api-python-client`; a new runtime
    dependency is named in the PR with its reason.
  - `YoutubeClient` is public on PyPI: a change that breaks an existing
    method's signature or return shape bumps the major version and says so.
  - Anything that writes to the account in bulk (unlike, delete from a
    playlist, change privacy) gets a dry-run mode that lists what it would do.
  - Every GitHub record authored by this implementer uses the signature
    `— Implementer (OpenCode, DeepSeek V4.1 Flash)`.
- **decided, and not to be re-opened:**
  - *Watch history cannot be read or modified through the API.* Google removed
    history from the Data API in 2016; `relatedPlaylists` no longer carries
    `watchHistory`. Deleting history is done on `myactivity.google.com`; browser
    automation for it is out (fragile, against YouTube's terms).
  - *The library has no history features* (owner, 2026-09-25: "let us drop
    history management", #62). The Takeout import, history page and actions on
    history (F-6, F-7) were removed before any release. They remain in tags
    v2.2.0–v2.5.1.
  - *`search.list(relatedToVideoId=…)` is gone* (removed in 2023), so related
    videos cannot be fetched; *`activities.list(mine=True)`* returns the
    owner's own activity, not recommendations.
  - *python-youtube (`pyyoutube`) was considered and not adopted* (2026-09-23):
    it covers the raw API but none of the convenience operations, and its OAuth
    is a manual paste with no token storage.
  - *yt-dlp with browser cookies (`:ythistory`) is not used for the history*
    (owner, 2026-09-25: "yt-dlp is not viable for a library I want to
    distribute"): the cookies are the whole Google login, reading the site this
    way is against YouTube's terms, and it gives no watch times.
  - *`thumbnails.set` takes a local file, not a URL* (max 2 MB), and needs a
    phone-verified channel; videos **uploaded** through an unaudited API project
    are locked private, so uploads happen in Studio and the API does the
    metadata, thumbnail and publishing.
- **open work:** `ROADMAP.md`, and GitHub issues on `diegoami/youtube3`.
- **owner decisions:**
  1. **Python 3.11+.** Raised from 3.10 on 2026-09-23 because
     `google.api_core` stops releasing for 3.10 after its end of life on
     2026-10-04.
  2. **Review:** the owner decision on 2026-09-23 was Claude Code only with an
     independent review at milestones. On 2026-09-27 the owner amended it,
     quoting issue #88,
     "from now on **OpenCode implements** (DeepSeek), and **a model from a
     different family reviews** each milestone (Claude Code, or GPT-6 Luna in
     OpenCode)." This amends the former Claude-Code-only decision. Milestones
     are tags, review is per milestone rather than per PR, and the owner runs
     the review-handoff prompt in a fresh session.
  3. **Records live on GitHub.** The proposal issue is the design record; the
     milestone issue, its verdict comment and `review` issues are the review
     record; there are no `design/` or `reviews/` directories. The completion
     note is a comment on the proposal issue when its PR merges. Implementation
     does not wait for a proposal review: the owner's go starts the branch.
  4. **`merge: auto`**, under the conditions in **Merging**. Pull requests do
     not wait for milestone review; PyPI uploads stay with the owner.
  5. **License: BSD-3-Clause**, with a `LICENSE` file, replacing the bare
     "BSD License" published up to 1.2.5 (#7). Chosen by the owner on
     2026-09-23.
- **provenance:** OpenCode mode adopted from `diegoami/harness_template` tag
  `r5` (commit `f22685d884c08381c5c4d6dcc3786aa394467c00`), on 2026-09-27.
  The project had adopted the shared principles and
  project slot from harness `r4`; this change moves the slot and tool-neutral
  process here from `CLAUDE.md`, while `CLAUDE.md` retains only its
  Claude-specific reviewer role.

<!-- SLOT:END -->
