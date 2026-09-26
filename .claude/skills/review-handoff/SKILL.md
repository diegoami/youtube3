---
name: review-handoff
description: Write the prompt the owner runs in a different model (Codex, DeepSeek, OpenCode, or another tool) so it independently reviews a milestone, a vX.Y.Z tag candidate on master, and records the result on GitHub. Use when a milestone is called or proposed (CLAUDE.md, "Milestones and the independent review"), for a re-review after a BLOCK, and whenever the owner asks for a review prompt. Also use when the owner says a review is in, to process it and, on AGREE, to tag.
---

# Review handoff

A milestone is a **tag**, a point in time (`CLAUDE.md`, "Milestones and the
independent review"). Proposals and pull requests are not milestones and get
no prompt; at most say in one line that a review is possible, and write the
prompt only if the owner asks.

Claude implements; a different model reviews, in whatever tool the owner
picks. At each milestone, give the owner one prompt in a single fenced `text`
block with nothing else in it. Tell the owner to run it in a **fresh
session** of that tool: a reused session carries its earlier conclusions. The
reviewer starts with no context and posts its results to GitHub itself, so
the prompt has to carry everything it needs, and it must not assume a tool.

Pull requests do not wait for the review; the tag does.

This repository has no `AGENTS.md`. The prompt's first line makes the tool
the reviewer; a tool that reads `CLAUDE.md` on its own finds the same
handover at the top of its milestone section. If the tool sandboxes network
access, every `gh` call needs it, and so does the first step, `git fetch`:
tell the owner to approve those calls when asked. A reviewer's clone is
often left at the previous tag, and a partial clone cannot read the new
commits' trees without the network ("fatal: unable to read tree"), so the
prompt always fetches before it checks out.

## Open the milestone issue first

`gh issue create --label milestone --title "Milestone vX.Y.Z"`, with:

- the candidate: `git rev-parse origin/master` after `git fetch`, the full
  SHA; `git status` clean and the checkout at that SHA;
- the previous milestone tag (`git describe --tags --abbrev=0 --match 'v*'`)
  and `git log --oneline --merges <previous tag>..<candidate>`: the pull
  requests since;
- the gate results on the candidate: its CI run and G1–G4 run locally;
- G5: the owner's live check and its result, or "not needed" when no API
  call changed;
- the owner decisions made since the previous tag.

## Fill in before writing

- **Repo**: `gh repo view --json nameWithOwner --jq .nameWithOwner`.
- **Thread**: the milestone issue.
- **Candidate**: the full SHA from the issue. A review of a moved `master`
  wastes a round: if `master` moves before the review starts, update the
  issue and the prompt, or tell the reviewer to stay on the candidate.
- **Diff to review**: `git diff <previous tag>..<candidate>`.
- **What changed and why**: one line per pull request since the previous
  tag. Do not argue for the changes.
- **Claims to verify**: the specific things the work says are true, with
  `file:line`. These are what the reviewer checks hardest.
- **Checks already run**: each gate from the `CLAUDE.md` gates table, its
  result and pass count, and what it would have caught. The reviewer should
  aim at what those checks cannot see.
- **Known owner decisions**: the standing ones are in the template; add the
  milestone's own.
- **Labels**: `gh label list`. `milestone`, `review`, `proposal`, `bug`,
  `robustness`, `tests`, `design`, `cleanup` and `documentation` should all
  exist (`gh label create review --description "Found by an independent
  review"`).

## Template

```text
You are the independent reviewer for <owner/repo>, working from a
review-handoff prompt: this prompt defines your job. Claude did this work. Do
not trust its description, its commit messages or its docs. Verify everything
against the code.

MILESTONE: <vX.Y.Z>, the tag to be created on the candidate if you agree
THREAD: <milestone issue URL>
CANDIDATE: master at <full sha>. First run git fetch origin --tags (it needs
network access; ask for it), then git checkout --detach <full sha>. If the
checkout fails with "unable to read tree", run git fetch --refetch origin and
try again. Stop and say so only if it still fails. PREVIOUS TAG: <vA.B.C>.

WHAT CHANGED: <one line per pull request since the previous tag>

CLAIMS TO VERIFY:
- <claim> (<file:line>)

ALREADY RUN: <gate: result, what it would catch>. Look for what these cannot
see.

KNOWN OWNER DECISIONS (not defects):
- The owner decisions and the "decided, and not to be re-opened" list in
  CLAUDE.md's project slot: watch history is not in the API, python-youtube
  was not adopted, uploads stay in YouTube Studio.
- Do not run anything against the YouTube API. The live gate (G5) writes to
  the owner's real account and needs the owner's OAuth credentials, which you
  do not have and must not look for.
- <this milestone's own, or "none">

Before anything else, read the repository's CLAUDE.md and PRINCIPLES.md. The
project slot in CLAUDE.md lists the files you must never read or echo
(client_secrets*.json, youtube.dat, token.json, Takeout exports, .env*) and
the gates table. Its principles and rules are the standard.

Run the offline gates yourself, from the gates table (G1 compile, G2 install,
and the unit tests, lint and CI once they exist), and say what each printed.

Review git diff <previous tag>..<sha>, and follow it into any file it touches
or relies on. Look hardest at correctness and edge cases in
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
     - Severity: MUST-FIX (a defect these changes introduce or fail to
       resolve, that should be fixed before the tag), SHOULD, or OUT OF
       SCOPE (not caused by these changes)
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

- Read the verdict comment on the milestone issue and every issue it lists
  (`gh issue view <n>`). Check that the SHA it names is the candidate.
- Reproduce each finding yourself before acting on it. A reviewer can be wrong,
  and so can you.
- MUST-FIX and SHOULD: fix it in an ordinary PR with `Fixes #n`, or rebut it
  with evidence in a comment on the issue and leave the close to the owner.
  OUT OF SCOPE: leave the issue for its own change. Owner decisions: put them
  to the owner with a recommended default. Nits: your call, and say which you
  took.
- Reply on the milestone issue with what happened to each finding. Write the
  body with the Write tool and pass it with `--body-file` (UTF-8, no BOM).
- **BLOCK**: once the MUST-FIX PRs have merged, move the candidate to the new
  `master` commit in the issue and give the re-review prompt, unasked. A
  third round that does not end in AGREE goes to the owner
  (`PRINCIPLES.md`).
- **AGREE**: confirm that G5 is recorded when the milestone changed an API
  call; if not, ask the owner and wait. Then tag exactly the reviewed SHA
  (`git tag -a vX.Y.Z <sha> -m "Milestone vX.Y.Z: AGREE by <reviewer>"`,
  `git push origin vX.Y.Z`), post the completion note on the milestone issue
  (each item and its evidence), and close it. Uploading to PyPI is the
  owner's.
