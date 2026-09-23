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
- Claude **does not spawn its own reviewer**. For a non-trivial change that is
  not a milestone, Claude verifies the work itself and says how in the PR:
  each gate it ran, its result, and what it would have caught had the code
  been wrong (`PRINCIPLES.md`, the six gates disciplines).
- A finding Claude disagrees with goes to the owner, not around the reviewer.
- Merging is `merge: auto`; the conditions are under **Merging** below.

### Independent review at milestones

*Reviewer: if a review-handoff prompt brought you here, that prompt defines
your job; this file is the standard you review against.*

At each milestone Claude gives the owner a prompt to run in a **different
model**, in whatever tool the owner picks (Codex, DeepSeek, OpenCode, or
another), in a fresh session every time. Nothing here assumes one tool.
**A milestone PR does not merge before its independent review**: it waits for
an AGREE, or for the owner to say to merge without one. A proposal's review
does not hold the branch; the owner's go on the proposal starts it. The
review is recorded on the thread the milestone already has:

| Milestone | Thread | Offer the prompt |
|---|---|---|
| Proposal written (a `ROADMAP.md` request shaped into its block) | the `proposal` issue carrying the block | with the proposal |
| PR that implements a proposal, gates green | the PR (it says `Closes #n` for the proposal) | when the PR is ready to merge |
| Release staged | the `release/X.Y.Z` PR, with the built sdist and wheel checksums in its body | before the owner publishes to PyPI |

**Nothing else gets a review prompt by default**: not tooling or CI fixes
without a proposal, not wording or docs changes, not small fixes inside an
agreed proposal (the release review covers them). At most a one-line
mention that a review is possible; the prompt only if the owner asks. A
**re-review** of a milestone PR is due when a BLOCK was answered with fixes,
or when commits after an AGREE go beyond the findings that review raised;
Claude writes its prompt without being asked, because the merge waits on it.

Every milestone PR body carries a `Review:` line that Claude keeps current:
`not run`, `AGREE at <sha>`, or `BLOCK at <sha>: #n, #m`. A review of a PR
already merged (one the owner merged without review) runs against the merge
commit; its findings are ordinary issues for a later PR.

The reviewer posts to GitHub itself, and nothing is pasted back:

- **one issue per reproduced finding**, labelled `review` plus a category
  label (`bug`, `robustness`, `tests`, `design`, `cleanup`,
  `documentation`), linking back to the thread and the SHA;
- **always one verdict comment** on the thread: AGREE, or BLOCK when any
  finding is MUST-FIX; the SHA reviewed, the issues it opened, what it
  checked and found clean. A review that finds nothing still leaves a
  record.

Severities: **MUST-FIX** (fixed before merging), **SHOULD**, and **OUT OF
SCOPE** (not caused by the change). The round ceiling in `PRINCIPLES.md` applies to milestone reviews.

The `review-handoff` skill (`.claude/skills/review-handoff/SKILL.md`) holds
the prompt template. When the owner says the review is in: read it from
GitHub, reproduce each finding before acting on it, and fix it (`Fixes #n`
in the PR) or rebut it with evidence on the issue. Owner decisions go to the
owner with a recommended default, not into the code.

### Merging

Claude merges a pull request itself (`gh pr merge --merge --delete-branch`)
when all of these hold, and records in the PR which ones it checked:

1. every gate in the gates table that the diff can affect is green **on the
   PR's head**, with the output summarised in the PR body, and CI is green
   on that head;
2. no open MUST-FIX issue names the PR, and no BLOCK verdict on the current
   head is unanswered;
3. **for a milestone PR**, the independent verdict is AGREE on the current
   head, or on an earlier head where every later commit only answers that
   review's findings (listed in the PR) — or the owner has said to merge
   without review, which the PR records;
4. the owner has not asked to hold it;
5. it is not a release: tagging `vX.Y.Z` and uploading to PyPI are the
   owner's, always.

Process changes (`PRINCIPLES.md`, `CLAUDE.md`, `.claude/**`) merge on the
same conditions (owner decision 4).

While a milestone PR waits for its review, Claude may start the next
unblocked request on its own branch.

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
  it). `build/`, `dist/`, `.eggs/`, `*.egg-info/`, `__pycache__/` —
  generated. `.idea/` — editor state.
- **never read or echo:** `client_secrets*.json` anywhere (the samples expect
  `samples/client_secrets.json`); `youtube.dat` (the oauth2client token
  store) and `token.json` or any other saved OAuth token; Google Takeout
  exports (`Takeout/`, `takeout-*.zip`); `.env*`; `~/.pypirc` and PyPI
  tokens. Never print an access or refresh token, an `Authorization` header
  or an API key, not even in test output.
- **merge:** auto — the conditions are in **Merging** above.
- **design:** none — see owner decision 3.
- **the gates table:**

  | gate | command | covers | runs | repeats | failure model |
  |---|---|---|---|---|---|
  | G1 compile | `python -m compileall -q youtube3 samples tests` | every module parses, samples included (they have no tests) | every PR, CI | 1 | deterministic |
  | G2 lint | `ruff check` | the `pyproject.toml` rule set (`E4 E7 E9 F B`) over `youtube3/`, `samples/`, `tests/` | every PR, CI | 1 | deterministic |
  | G3 unit tests | `pytest -q` | the client's requests and results over canned responses (`tests/conftest.py`: the bundled discovery document, `HttpMockSequence`, no network); known bugs pinned as strict `xfail` | every PR, CI | 1 | deterministic, offline; a failure is a real failure |
  | G4 package | `python -m build`, `twine check --strict`, install the wheel in a fresh venv and `import youtube3` outside the checkout | the metadata, the declared dependencies resolve, and the package imports from an install | every PR, CI | 1 | deterministic given the package index; a network error is re-run once and recorded |
  | G5 live | the affected `samples/*.py` against the owner's account | real API behaviour: OAuth, quota, what the owner would see on YouTube | milestone PRs that change an API call, **only with the owner's go** — it writes to a real account | 1 | a live service: a failure is reproduced once before it is believed |

  CI (`.github/workflows/ci.yml`) runs G1–G4 on Python 3.11 and 3.14 for
  every pull request and every push to `master`; a red CI does not merge.
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
     milestones**, as in discola-web and Geoclick2027, except that a
     milestone PR waits for it before merging. This replaces the
     fresh-context review of every non-trivial change: outside milestones,
     Claude's self-verification in the PR is the record. The verdict protocol
     of `PRINCIPLES.md` (target proof, rounds, materiality, owner decisions,
     defect path) governs the milestone reviews.
  3. **Records live on GitHub.** The proposal issue is the design record; the
     verdict comment and the `review` issues are the review record; there are
     no `design/` or `reviews/` directories. The completion note is a comment
     on the proposal issue when its PR merges. Implementation does not wait
     for a proposal review: the owner's go on the proposal starts the branch.
  4. **`merge: auto`**, with the conditions in **Merging** above. Like
     `PRINCIPLES.md`'s ("review clean plus gates green"), but the review
     condition applies to milestone PRs only. Releases stay with the owner.
     Process changes first waited for the owner too; on 2026-09-23 the owner
     ruled that a green PR that is not a milestone is Claude's to merge,
     process changes included.
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
