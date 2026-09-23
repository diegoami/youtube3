---
name: review-handoff
description: Write the prompt the owner runs in a different model (Codex, DeepSeek, OpenCode, or another tool) so it independently reviews the repository at a milestone and records the result on GitHub. Use when a proposal issue is written, when a PR that implements one is ready to merge, or when a release is staged on its release/X.Y.Z PR (the milestones in CLAUDE.md), and whenever the owner asks for a review prompt. Also use when the owner says a review is in, to process it.
---

# Review handoff

First check the milestone is one: `CLAUDE.md` ("Independent review at
milestones") lists them. A tooling or CI fix without a proposal, a docs or
wording change, a small fix inside an agreed proposal, or a re-review is not.
Do not write a prompt for it; at most say in one line that a review is
possible, and write the prompt only if the owner asks.

Claude implements; a different model reviews, in whatever tool the owner
picks. At each milestone, give the owner one prompt in a single fenced `text`
block with nothing else in it. Tell the owner to run it in a **fresh
session** of that tool: a reused session carries its earlier conclusions. The
reviewer starts with no context and posts its results to GitHub itself, so
the prompt has to carry everything it needs, and it must not assume a tool.

The review is offered, never waited on. Do not stop work for it: set the PR
body's `Review:` line to `not run`, and update it when a verdict arrives
(`AGREE at <sha>`, or `BLOCK at <sha>: #n, #m`).

This repository has no `AGENTS.md`. The prompt's first line makes the tool
the reviewer; a tool that reads `CLAUDE.md` on its own finds the same
handover at the top of its review section. If the tool sandboxes network
access, every `gh` call needs it: tell the owner to approve those calls when
asked.

## Fill in before writing

- **Repo**: `gh repo view --json nameWithOwner --jq .nameWithOwner`.
- **Milestone and thread**: proposal (the `proposal` issue), PR (the PR that
  closes a proposal), or release (the `release/X.Y.Z` PR).
- **Head SHA**: `git rev-parse HEAD` on the branch under review, pushed. A
  review of a stale head wastes a round. For a PR already merged, the merge
  commit, and the review reads `git diff <sha>^1 <sha>`.
- **Diff to review**: proposal, the issue text; PR, `git diff master...<sha>`;
  release, `git diff <last tag>..<sha>`, plus the sdist and wheel checksums
  in the PR body.
- **What changed and why**: two or three sentences. Do not argue for the
  change. For a release, one line per merged PR since the last tag.
- **Claims to verify**: the specific things the work says are true, with
  `file:line`. These are what the reviewer checks hardest.
- **Checks already run**: each gate from the `CLAUDE.md` gates table, its
  result and pass count, and what it would have caught. The reviewer should
  aim at what those checks cannot see.
- **Known owner decisions**: questions already put to the owner, so the
  reviewer does not report them as defects. The standing ones are in the
  template; add the milestone's own.
- **Labels**: `gh label list`. `review`, `proposal`, `bug`, `robustness`,
  `tests`, `design`, `cleanup` and `documentation` should all exist
  (`gh label create review --description "Found by an independent review"`).

## Template

```text
You are the independent reviewer for <owner/repo>, working from a
review-handoff prompt: this prompt defines your job. Claude did this work. Do
not trust its description, its commit messages or its docs. Verify everything
against the code.

MILESTONE: <proposal | pull request | staged release>
THREAD: <issue or PR URL>
HEAD: <branch> at <sha>. Check out that SHA before you start, and stop and say
so if you cannot.

WHAT CHANGED: <two or three sentences; for a release, one line per PR>

CLAIMS TO VERIFY:
- <claim> (<file:line>)

ALREADY RUN: <gate: result, what it would catch>. Look for what these cannot
see.

KNOWN OWNER DECISIONS (not defects):
- The owner decisions and the "decided, and not to be re-opened" list in
  CLAUDE.md's project slot: watch history is not in the API, python-youtube
  was not adopted, uploads stay in YouTube Studio.
- Do not run anything against the YouTube API. The live gate (G3) writes to
  the owner's real account and needs the owner's OAuth credentials, which you
  do not have and must not look for.
- <this milestone's own, or "none">

Before anything else, read the repository's CLAUDE.md and PRINCIPLES.md. The
project slot in CLAUDE.md lists the files you must never read or echo
(client_secrets*.json, youtube.dat, token.json, Takeout exports, .env*) and
the gates table. Its principles and rules are the standard.

Run the offline gates yourself, from the gates table (G1 compile, G2 install,
and the unit tests, lint and CI once they exist), and say what each printed.

Review <the proposal | the diff against master, git diff master...<sha> | the
merged diff, git diff <sha>^1 <sha> | the release diff, git diff <last
tag>..<sha>, and the checksums in the PR body>, and follow it into any file it
touches or relies on. Look hardest at correctness and edge cases in
pagination and quota use, anything that writes to the account without a dry
run, secrets or tokens that could be printed or committed, breaks in the
public YoutubeClient API, and missing or vacuous tests. Problems elsewhere in
the repository count too, as out of scope.

Rules:
- Do not edit files, commit or push. Your only writes are the GitHub issues
  and the one comment described below, made with the gh CLI.
- Reproduce every finding: cite file:line, and give the command, the input or
  the reasoning that shows it. Leave out anything you could not reproduce.
- Do not report style preferences.
- Before opening an issue, search open issues (gh issue list --search) and
  comment on an existing one instead of duplicating it.
- Write issue and comment bodies to a file as UTF-8 without a BOM and pass
  them with --body-file.

1. For each finding, open one issue:
   gh issue create --label review --label <bug|robustness|tests|design|cleanup|documentation>
   Title: the defect, stated plainly.
   Body:
     - Severity: MUST-FIX (a defect this change introduces or fails to
       resolve, that should be fixed before merging), SHOULD, or OUT OF
       SCOPE (not caused by this change)
     - Found by: review of <THREAD> at <sha>
     - What: the defect, with file:line and a reproduction
     - Why it matters: what the owner or a library user would notice
     - Suggested fix: the smallest change that resolves it
     - Effort: S, M or L
     - Signed: — Reviewer (<tool>, <model>)

2. Then, always, even if you found nothing, post one comment on THREAD:
   VERDICT: AGREE | BLOCK        (BLOCK if any MUST-FIX issue was opened)
   Reviewed: <sha>
   Issues opened: #n (MUST-FIX), #m (SHOULD), ... or "none"
   Owner decisions: questions only the owner can settle, or "none"
   Nits: one line each, or "none" (nits do not get issues)
   Checked and clean: what you verified and found correct
   — Reviewer (<tool>, <model>)
```

## When the owner says the review is in

- Read the verdict comment on the thread and every issue it lists
  (`gh issue view <n>`), and update the PR body's `Review:` line. Note whether
  the SHA it names is the current head or an earlier one.
- Reproduce each finding yourself before acting on it. A reviewer can be wrong,
  and so can you.
- MUST-FIX and SHOULD: fix it, with `Fixes #n` in the PR, or rebut it with
  evidence in a comment on the issue and leave the close to the owner. If the
  PR is already merged, the fix is a new PR. Recommend which fixes belong
  before the merge; the owner decides. OUT OF SCOPE: leave the issue for its
  own change. Owner decisions: put them to the owner with a recommended
  default. Nits: your call, and say which you took.
- Reply on the thread with what happened to each finding. Write the body with
  the Write tool and pass it with `--body-file` (UTF-8, no BOM).
- Rerun the gates after any fix. Do not offer a re-review prompt; write one
  only if the owner asks.
